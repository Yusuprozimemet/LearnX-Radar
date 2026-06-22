"""Entry point. Orchestrates the daily run:

    scrape -> dedup -> extract skills -> score gaps -> write brief
           -> plan curriculum -> generate dialogue -> build audio
           -> deliver -> persist state

Each stage is wrapped so one failure produces a clear message instead of a
silent half-run; failures are collected and DM'd to the owner at the end of the
run (see _report) so an unattended cron can't degrade silently.
"""
import asyncio
from datetime import date
from pathlib import Path

import config
from agents import (
    devto_agent,
    github_trending_agent,
    hn_front_agent,
    hn_hiring_agent,
    lobsters_agent,
    reddit_agent,
    stackoverflow_agent,
)
from dashboard import builder as dashboard
from delivery import devto_publisher, email_sender, telegram_recall, telegram_sender
from dutch import audio as dutch_audio
from dutch import coach as dutch_coach
from dutch import lesson as dutch_lesson
from dutch import progress as dutch_progress
from dutch import review as dutch_review
from dutch import trainer as dutch_trainer
from dutch import wordlist as dutch_wordlist
from learnx import audio_builder, curriculum, dialogue
from radar import brief_writer, gap_scorer, privacy, skill_extractor
from storage import (
    apply_learned_aliases,
    dutch_unsubmitted_streak,
    filter_new,
    load_brief,
    load_dutch_memory,
    load_memory,
    load_seen,
    load_trending_history,
    mark_seen,
    previous_lesson,
    record_dutch_lesson,
    record_dutch_recall,
    record_dutch_review,
    record_lesson,
    record_lesson_rating,
    review_token,
    save_brief,
    save_dutch_lesson,
    save_dutch_memory,
    save_dutch_progress,
    save_last_scored,
    save_memory,
    save_review,
    save_seen,
    save_trending_history,
    slugify,
)
from storage.state import DUTCH_LESSONS_DIR

OUTPUT_DIR = Path(__file__).parent / "output"

# Stage failures collected across the run; _report() DMs them to the owner so the
# per-stage guards (which keep the run alive) can't also hide a dying channel.
_failures: list[str] = []


def _fail(stage: str, exc: Exception) -> None:
    print(f"[{stage}] failed: {exc}")
    _failures.append(f"{stage}: {exc}")


def _report() -> None:
    """DM the collected failures to the owner chat. Best-effort: if Telegram itself
    is down this can't help, but partial failures (one source, one channel) reach
    the owner via the surviving DM path."""
    if not _failures or not config.RUN_REPORT_ENABLED:
        return
    text = f"⚠️ LearnX-Radar run had {len(_failures)} failure(s) on {date.today():%Y-%m-%d}:\n"
    text += "\n".join(f"• {f}" for f in _failures)
    try:
        telegram_sender.send_report(text)
    except Exception as exc:
        print(f"[report] could not send failure report: {exc}")


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
        ("reddit", reddit_agent),
        ("hn_front", hn_front_agent),
        ("lobsters", lobsters_agent),
    )
    for name, agent in no_arg_sources:
        try:
            fetched = agent.fetch()
            print(f"[{name}] fetched {len(fetched)} item(s)")
            items.extend(fetched)
        except Exception as exc:
            _fail(f"{name} fetch", exc)

    try:
        fetched = stackoverflow_agent.fetch(memory.get("so_counts", {}))
        print(f"[stackoverflow] fetched {len(fetched)} item(s)")
        items.extend(fetched)
    except Exception as exc:
        _fail("stackoverflow fetch", exc)

    # Redact PII (emails/phones/handles) from every item's free text at ingestion,
    # before dedup, the LLM, persistence, delivery, or the Perplexity link see it.
    free_text_fields = {"title", "text", "meta"}
    known_sources = {
        "GitHub Trending", "HN Hiring", "dev.to", "Stack Overflow",
        "Reddit", "HN Front Page", "Lobste.rs",
    }
    safe_exempt = {"id", "source", "url"}
    for item in items:
        fields = free_text_fields
        if item.get("source") not in known_sources:
            fields = [
                key
                for key, value in item.items()
                if isinstance(value, str) and key not in safe_exempt
            ]
        for field in fields:
            value = item.get(field)
            if isinstance(value, str):
                item[field] = privacy.scrub(value)

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
        dutch = load_dutch_memory() if config.DUTCH_ENABLED else None
        path = dashboard.build(memory, scored, today_skill, dutch=dutch)
        print(f"[dashboard] wrote {path}")
    except Exception as exc:
        _fail("dashboard build", exc)


def _ingest_inbound(memory: dict) -> None:
    """Fold pending deep-link feedback (one acknowledged getUpdates batch) into
    state, saving immediately so the fold-in survives even if a later stage fails:

    - dev-lesson star ratings -> skill_memory lesson entries (the quality signal
      for the developer track), and
    - Dutch trainer recall reports (v9 day 33) -> dutch_memory SR state, BEFORE
      today's word selection so a failed word is already due.

    Both ride the same fetch because acknowledging the batch drops every pending
    update. Guarded: a Telegram hiccup degrades to exposure-only scheduling and a
    missed rating, never blocks the run."""
    if not (config.DUTCH_RECALL_ENABLED or config.LESSON_RATING_ENABLED):
        return
    try:
        inbound = telegram_recall.fetch_inbound()
    except Exception as exc:
        _fail("telegram inbound", exc)
        return
    if config.LESSON_RATING_ENABLED and inbound["ratings"]:
        applied = sum(record_lesson_rating(memory, d, n) for d, n in inbound["ratings"])
        if applied:
            save_memory(memory)
        print(f"[rating] {len(inbound['ratings'])} rating(s), {applied} lesson(s) stamped")
    if not config.DUTCH_RECALL_ENABLED:
        return
    if config.dutch_multiuser_active():
        _ingest_dutch_multiuser(inbound)
    elif inbound["recall"]:
        try:
            dmem = load_dutch_memory()
            applied = sum(record_dutch_recall(dmem, d, marks) for d, marks in inbound["recall"])
            if applied:
                save_dutch_memory(dmem)
            print(f"[dutch] recall: {len(inbound['recall'])} report(s), {applied} word(s) updated")
        except Exception as exc:
            _fail("dutch recall", exc)


def _ingest_dutch_multiuser(inbound: dict) -> None:
    """Fold each allowlisted learner's recall (dr_) and cross-day review (rv_) into
    their OWN dutch_memory_<chatid>.json. One getUpdates batch carried them all,
    keyed by sender chat id; per-user failures are isolated so one bad file can't
    drop another learner's feedback."""
    recall = inbound.get("recall_by_user", {})
    review = inbound.get("review_by_user", {})
    for chat_id in sorted(set(recall) | set(review)):
        try:
            dmem = load_dutch_memory(chat_id)
            applied = 0
            for d, marks in recall.get(chat_id, []):
                applied += record_dutch_recall(dmem, d, marks)
            for d, marks in review.get(chat_id, []):
                applied += record_dutch_review(dmem, d, marks)
            if applied:
                save_dutch_memory(dmem, chat_id)
            print(f"[dutch] {chat_id}: folded {applied} recall/review outcome(s)")
        except Exception as exc:
            _fail(f"dutch recall {chat_id}", exc)


def _dutch_pause_payload(backlog: int) -> dict:
    """Nudge shown instead of a new lesson while the learner is behind (v10 day 37).

    No audio, no quiz — just a short note pointing back to the trainer, where the
    unfinished lessons still live (dutch_lesson.json is the last one generated). The
    delivery layer renders any payload with `markdown`, so this rides the normal DM
    and email; an empty quiz_words means no quiz button."""
    md = (
        "## 🇳🇱 Dutch — even pauze (paused)\n\n"
        f"_Je hebt **{backlog}** lessen nog niet afgerond._ "
        f"_(You have {backlog} lessons you haven't finished yet.)_\n\n"
        "No new words today — finish one and **save your results** to pick the loop "
        "back up where you left off."
    )
    if config.DUTCH_TRAINER_ENABLED:
        md += f"\n\n🎧 _Maak er één af (finish one):_ {config.TRAINER_URL}"
    return {"markdown": md, "mp3_path": None, "quiz_words": []}


def _build_dutch(today_skill: str | None) -> tuple[dict | None, dict | None]:
    """Build the daily Dutch lesson: (delivery_payload, persist_state).

    Fully isolated — disabled via config or any failure returns (None, None) so the
    dev lesson always ships. The quiz targets YESTERDAY's words, read from memory
    here before record_dutch_lesson (in the persist step) overwrites last_words.
    """
    if not config.DUTCH_ENABLED:
        return None, None
    try:
        today = date.today()
        # Recall reports were already folded in by _ingest_inbound (and saved), so
        # this load sees the reset due dates before word selection.
        dmem = load_dutch_memory()
        # Backlog backpressure (v10 day 37): if recent lessons keep going unfinished
        # (no recall report), don't pile on a new one — that just buries the learner
        # and lets SR drift. Pause and nudge instead; one saved result resumes it.
        # No state returned, so the paused day isn't itself logged as a backlog item.
        if config.DUTCH_BACKLOG_PAUSE_AFTER:
            backlog = dutch_unsubmitted_streak(dmem)
            if backlog >= config.DUTCH_BACKLOG_PAUSE_AFTER:
                print(f"[dutch] paused: {backlog} unfinished lesson(s) — awaiting a result")
                return _dutch_pause_payload(backlog), None
        bank = dutch_wordlist.load()
        theme = dutch_wordlist.theme_for(today)
        # Mistake-driven coach (v10 day 36): detect words the learner keeps failing
        # and, if any, let one LLM call pick today's focus. Fully guarded — any
        # failure falls back to mechanical selection so the lesson always ships.
        force_ids: list[str] = []
        directive = ""
        if config.DUTCH_COACH_ENABLED:
            try:
                struggling = dutch_coach.detect_struggling(dmem, bank)
                if struggling:
                    cplan = dutch_coach.plan(struggling)
                    force_ids = cplan["focus_ids"]
                    directive = cplan["directive"]
                    dutch_coach.append_log(cplan, struggling, when=today)
                    print(f"[dutch] coach: {len(struggling)} struggling, "
                          f"focus {force_ids or '(none)'}")
            except Exception as exc:
                _fail("dutch coach", exc)
        new_w, review_w = dutch_wordlist.select_for_today(
            bank,
            dmem,
            today,
            theme=theme,
            new_count=config.DUTCH_NEW_WORDS_PER_DAY,
            review_max=config.DUTCH_REVIEW_WORDS_MAX,
            force_review_ids=force_ids,
        )
        if not new_w and not review_w:
            print("[dutch] no words to teach today")
            return None, None
        topic = today_skill if (theme == "tech" and config.DUTCH_THEME_TECH_TIE_IN) else None
        dlesson = dutch_lesson.build(
            new_w,
            review_w,
            theme=theme,
            topic=topic,
            cefr=dmem.get("cefr", config.DUTCH_CEFR_START),
            directive=directive,
        )
        dutch_mp3: str | None = str(OUTPUT_DIR / f"dutch-{today:%Y%m%d}.mp3")
        timings: list[dict] = []
        try:
            timings = asyncio.run(dutch_audio.build(dlesson, dutch_mp3))
        except Exception as exc:
            _fail("dutch audio", exc)
            dutch_mp3 = None
        # Delft trainer JSON (v9 day 32): persist today's lesson (text + cloze +
        # audio seek map) for the Pages trainer. Needs the audio's timings, so it
        # only writes when the render succeeded; guarded — never blocks delivery.
        if config.DUTCH_TRAINER_ENABLED and dutch_mp3:
            try:
                save_dutch_lesson(
                    dutch_trainer.build_payload(dlesson, timings, Path(dutch_mp3).name)
                )
            except Exception as exc:
                _fail("dutch trainer", exc)
        payload = {
            "markdown": dlesson.markdown,
            "mp3_path": dutch_mp3,
            "quiz_words": dutch_wordlist.entries_for(bank, dmem.get("last_words", [])),
        }
        state = {
            "memory": dmem,
            "word_ids": [w["id"] for w in new_w + review_w],
            "theme": theme,
            "audio": Path(dutch_mp3).name if dutch_mp3 else "",
            "summary": dlesson.summary,
        }
        print(f"[dutch] {theme} lesson: {len(new_w)} new, {len(review_w)} review")
        return payload, state
    except Exception as exc:
        _fail("dutch build", exc)
        return None, None


def _persist_dutch_multiuser(dutch_state: dict) -> None:
    """Record today's SHARED lesson into every learner's SR file and publish each
    learner's personal cross-day review (review/<token>.json). Generation stayed
    global (one lesson + audio); only SELECTION is per-user. Today's new words enter
    each schedule due later, so they don't appear in today's review — the review is
    genuinely the words each learner still owes. Per-user failures are isolated."""
    bank = dutch_wordlist.load()
    for chat_id in config.dutch_user_chat_ids():
        try:
            dmem = load_dutch_memory(chat_id)
            record_dutch_lesson(
                dmem,
                word_ids=dutch_state["word_ids"],
                theme=dutch_state["theme"],
                audio=dutch_state["audio"],
                summary=dutch_state["summary"],
            )
            payload = dutch_review.build(
                dmem, DUTCH_LESSONS_DIR, bank, max_items=config.DUTCH_REVIEW_MAX
            )
            # Store the published order so an rv_ report's positional marks map back.
            dmem["last_review"] = {"date": payload["generated"], "ids": payload["ids"]}
            save_dutch_memory(dmem, chat_id)
            save_review(review_token(chat_id), payload)
            print(f"[dutch] {chat_id}: SR updated, {len(payload['ids'])} review item(s)")
        except Exception as exc:
            _fail(f"dutch persist {chat_id}", exc)


def _run() -> None:
    config.validate()
    # Merge autonomously-learned skill aliases into config.SKILL_ALIASES before any
    # scoring, so _canonical collapses the variants the curator has accepted (v7 day26).
    apply_learned_aliases()
    memory = load_memory()

    # Fold in yesterday's deep-link feedback (lesson ratings + Dutch trainer recall)
    # before anything else: ratings land in memory ahead of the saves below, and
    # recall resets are on disk before the Dutch branch selects today's words.
    _ingest_inbound(memory)

    # Weekly personalization-waitlist CTA to the channel (fires only on its
    # configured weekday; runs before the early-return so a quiet day still posts).
    try:
        telegram_sender.post_waitlist()
    except Exception as exc:
        _fail("waitlist post", exc)

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

    # 2. Radar: score ALL scraped items (not just new ones) so the dashboard shows
    # the full demand picture on every run; novelty already sinks recently-taught
    # skills, so top() still picks a genuine gap to teach.
    mentions = skill_extractor.extract(items)
    profile = {"known": config.KNOWN_SKILLS, "goals": config.LEARNING_GOALS}
    # Prior-day rankings power the momentum multiplier (today isn't written until
    # save_trending_history below, so this is strictly history).
    scored = gap_scorer.score(mentions, memory, profile, history=load_trending_history())
    # Extraction maximizes recall (many candidates); MAX_SKILL_MENTIONS trims after
    # scoring so the brief/dashboard stay focused on the top N.
    skill = gap_scorer.top(scored)
    scored = scored[: config.MAX_SKILL_MENTIONS]
    # Persist the ranking so the dashboard can rebuild from committed state alone
    # (the Pages workflow has no API keys to re-run the radar).
    save_last_scored(scored, skill["skill"] if skill else None)
    # Also append today's ranking to the per-day archive so the dashboard's date
    # picker can replay any past day (last_scored.json only holds the latest run).
    save_trending_history(scored, skill["skill"] if skill else None)
    if skill is None:
        print("No teachable skill gap found today. Done.")
        _refresh_dashboard(memory, scored)
        return
    print(f"Today's skill: {skill['skill']} (score {skill.get('score')})")

    brief_md = brief_writer.write(skill, memory, items)
    brief_file = save_brief(skill["skill"], brief_md)  # committed; linked for Perplexity Q&A

    # 3. Learnx: brief -> curriculum -> dialogue -> audio.
    difficulty = config.LESSON_DIFFICULTY_OVERRIDE or skill.get(
        "suggested_difficulty", config.LESSON_DIFFICULTY_DEFAULT
    )
    units = curriculum.plan(brief_md, skill["skill"], difficulty=difficulty)
    action = brief_writer.action_step(brief_md)  # voiced in the outro as a call to action
    lines = dialogue.generate(
        units, skill["skill"], hook=skill.get("evidence", ""), action=action,
        difficulty=difficulty,
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Per-lesson filename (date + skill slug, like the brief) so several lessons on
    # the same day get distinct files/URLs/GUIDs instead of clobbering one another.
    mp3_path = str(OUTPUT_DIR / f"lesson-{date.today():%Y%m%d}-{slugify(skill['skill'])}.mp3")
    asyncio.run(audio_builder.build(lines, mp3_path))

    lesson = {
        "title": skill["skill"],
        "skill": skill["skill"],
        "summary": skill.get("evidence", ""),
        "difficulty": difficulty,
        "mp3_path": mp3_path,
        "brief_md": brief_md,
        "brief_file": brief_file,
    }

    # Recall quiz targets the PREVIOUS lesson (real spaced retrieval). memory has no
    # entry for today yet (record_lesson runs below), so this is genuinely prior;
    # absent on day one, so the senders' quiz button simply won't render. We load the
    # prior brief's text (not just its filename) so the quiz deep link embeds it as
    # Perplexity context — a missing/empty brief leaves the button unrendered.
    prev = previous_lesson(memory)
    if prev and prev.get("brief"):
        prev_brief_md = load_brief(prev["brief"])
        if prev_brief_md:
            lesson["quiz_skill"] = prev["skill"]
            lesson["quiz_brief_md"] = prev_brief_md

    # 3c. Dutch coach: build an independent A2 Dutch lesson and attach it to the
    # payload so each sender appends it. Isolated — never blocks the dev lesson.
    dutch_payload, dutch_state = _build_dutch(skill["skill"])
    if dutch_payload:
        lesson["dutch"] = dutch_payload

    # 4. Deliver (each channel independent).
    for name, sender in (("telegram", telegram_sender), ("email", email_sender)):
        try:
            sender.send(lesson)
        except Exception as exc:
            _fail(f"{name} send", exc)

    # 4b. Weekly cross-post to dev.to (draft) for reach/SEO — never blocks the run.
    try:
        devto_publisher.publish(lesson)
    except Exception as exc:
        _fail("devto cross-post", exc)

    # 5. Persist state only after the lesson was produced.
    mark_seen(seen, (item["id"] for item in new_items))
    save_seen(seen)
    record_lesson(
        memory,
        skill["skill"],
        title=lesson["title"],
        difficulty=difficulty,
        summary=lesson["summary"],
        audio=Path(mp3_path).name,
        brief=brief_file,
    )
    save_memory(memory)

    # 5b. Persist Dutch spaced-repetition state (separate file, separate concern).
    if dutch_state:
        if config.dutch_multiuser_active():
            _persist_dutch_multiuser(dutch_state)
        else:
            try:
                record_dutch_lesson(
                    dutch_state["memory"],
                    word_ids=dutch_state["word_ids"],
                    theme=dutch_state["theme"],
                    audio=dutch_state["audio"],
                    summary=dutch_state["summary"],
                )
                save_dutch_memory(dutch_state["memory"])
                # Publish the cross-device scorecard: the trainer's LESSEN scores are
                # localStorage (per-browser), so results submitted on the phone never
                # show on the computer. progress.json carries the server-side record to
                # every device. Synced once per day, with this run.
                save_dutch_progress(dutch_progress.build_progress(dutch_state["memory"]))
            except Exception as exc:
                _fail("dutch persist", exc)

    # 6. Regenerate the dashboard from the updated state + this run's ranking.
    _refresh_dashboard(memory, scored, skill["skill"])
    print("Done.")


def main() -> None:
    """Run the pipeline, then DM any stage failures to the owner. A hard crash is
    recorded and re-raised so the Actions run still goes red."""
    try:
        _run()
    except Exception as exc:
        _fail("run", exc)
        raise
    finally:
        _report()


if __name__ == "__main__":
    main()
