"""Entry point. Orchestrates the daily run:

    scrape -> dedup -> extract skills -> score gaps -> write brief
           -> plan curriculum -> generate dialogue -> build audio
           -> deliver -> persist state

Each stage is wrapped so one failure produces a clear message instead of a
silent half-run. The module stubs raise NotImplementedError until their v1 spec
day lands; the orchestration below is the contract they fill.
"""
import asyncio
from datetime import date
from pathlib import Path

import config
from agents import (
    devto_agent,
    github_trending_agent,
    hn_hiring_agent,
    stackoverflow_agent,
)
from dashboard import builder as dashboard
from delivery import email_sender, telegram_sender
from learnx import audio_builder, curriculum, dialogue
from radar import brief_writer, gap_scorer, skill_extractor
from storage import (
    filter_new,
    load_memory,
    load_seen,
    record_lesson,
    save_last_scored,
    save_memory,
    save_seen,
)

OUTPUT_DIR = Path(__file__).parent / "output"


def _scrape(memory: dict) -> list[dict]:
    """Run every agent; a failing source must not kill the run.

    Stack Overflow is special: it needs last week's tag counts (from memory) to
    compute a delta, so it's called with prior_counts instead of bare fetch().
    """
    items: list[dict] = []
    no_arg_sources = (
        ("github_trending", github_trending_agent),
        ("hn_hiring", hn_hiring_agent),
        ("devto", devto_agent),
    )
    for name, agent in no_arg_sources:
        try:
            fetched = agent.fetch()
            print(f"[{name}] fetched {len(fetched)} item(s)")
            items.extend(fetched)
        except Exception as exc:
            print(f"[{name}] fetch failed: {exc}")

    try:
        fetched = stackoverflow_agent.fetch(memory.get("so_counts", {}))
        print(f"[stackoverflow] fetched {len(fetched)} item(s)")
        items.extend(fetched)
    except Exception as exc:
        print(f"[stackoverflow] fetch failed: {exc}")

    return items


def _persist_so_counts(memory: dict, items: list[dict]) -> None:
    """Fold this run's Stack Overflow readings into memory['so_counts']."""
    counts = memory.setdefault("so_counts", {})
    for item in items:
        reading = item.get("_so_count")
        if reading:
            counts[reading["tag"]] = reading["total"]


def _refresh_dashboard(memory: dict, scored=None, today_skill=None) -> None:
    """Regenerate the static dashboard; never let it fail the run."""
    try:
        path = dashboard.build(memory, scored, today_skill)
        print(f"[dashboard] wrote {path}")
    except Exception as exc:
        print(f"[dashboard] build failed: {exc}")


def main() -> None:
    config.validate()
    memory = load_memory()

    # 1. Collect from all sources, then drop anything already taught.
    items = _scrape(memory)
    seen = load_seen()
    new_items = filter_new(items, seen)
    print(f"{len(new_items)} new of {len(items)} scraped")

    # Persist this run's Stack Overflow readings regardless of what follows, so
    # next week has a baseline to diff against even on a quiet day.
    _persist_so_counts(memory, items)
    save_memory(memory)

    if not new_items:
        print("Nothing new in the developer world today. Done.")
        _refresh_dashboard(memory)  # refresh coverage/archive even on a quiet day
        return

    # 2. Radar: extract skills, score the gap, pick today's topic.
    mentions = skill_extractor.extract(new_items)
    scored = gap_scorer.score(mentions, memory)
    skill = gap_scorer.top(scored)
    # Persist the ranking so the dashboard can rebuild from committed state alone
    # (the Pages workflow has no API keys to re-run the radar).
    save_last_scored(scored, skill["skill"] if skill else None)
    if skill is None:
        print("No teachable skill gap found today. Done.")
        _refresh_dashboard(memory, scored)
        return
    print(f"Today's skill: {skill['skill']} (score {skill.get('score')})")

    brief_md = brief_writer.write(skill, memory)

    # 3. Learnx: brief -> curriculum -> dialogue -> audio.
    difficulty = skill.get("suggested_difficulty", config.LESSON_DIFFICULTY_DEFAULT)
    units = curriculum.plan(brief_md, skill["skill"], difficulty=difficulty)
    lines = dialogue.generate(units, skill["skill"], hook=skill.get("evidence", ""))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    mp3_path = str(OUTPUT_DIR / f"lesson-{date.today():%Y%m%d}.mp3")
    asyncio.run(audio_builder.build(lines, mp3_path))

    lesson = {
        "title": skill["skill"],
        "skill": skill["skill"],
        "summary": skill.get("evidence", ""),
        "difficulty": difficulty,
        "mp3_path": mp3_path,
        "brief_md": brief_md,
    }

    # 4. Deliver (each channel independent).
    for name, sender in (("telegram", telegram_sender), ("email", email_sender)):
        try:
            sender.send(lesson)
        except Exception as exc:
            print(f"[{name}] send failed: {exc}")

    # 5. Persist state only after the lesson was produced.
    seen.update(item["id"] for item in new_items)
    save_seen(seen)
    record_lesson(
        memory,
        skill["skill"],
        title=lesson["title"],
        difficulty=difficulty,
        summary=lesson["summary"],
        audio=Path(mp3_path).name,
    )
    save_memory(memory)

    # 6. Regenerate the dashboard from the updated state + this run's ranking.
    _refresh_dashboard(memory, scored, skill["skill"])
    print("Done.")


if __name__ == "__main__":
    main()
