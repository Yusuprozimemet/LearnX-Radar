"""Track B orchestration: build, ingest, and persist the daily Dutch lesson.

Extracted from main.py so the daily spine stays a readable sequence and all of
Track B lives next to the rest of the `dutch/` package. The pipeline (frozen
bank -> CEFR/coach selection -> Delft audio -> trainer JSON) and its
spaced-repetition persistence are here; main.py only wires the dev lesson to it.

Failures are reported through a `fail(stage, exc)` callback (main passes its
own collector) so the per-stage prefixes the Status tab groups on ("dutch coach",
"dutch audio", "dutch trainer", "dutch build", "dutch persist", "dutch recall",
"cohort publish") are unchanged by the move. Every step is guarded: a disabled
config or any failure yields (None, None) so the dev lesson always ships.
"""
import asyncio
from collections.abc import Callable
from datetime import date
from pathlib import Path

import config
from dutch import audio as dutch_audio
from dutch import coach as dutch_coach
from dutch import cohort as dutch_cohort
from dutch import lesson as dutch_lesson
from dutch import progress as dutch_progress
from dutch import review as dutch_review
from dutch import trainer as dutch_trainer
from dutch import wordlist as dutch_wordlist
from storage import (
    dutch_unsubmitted_streak,
    load_dutch_memory,
    record_dutch_lesson,
    record_dutch_recall,
    record_dutch_review,
    review_token,
    save_cohort,
    save_dutch_lesson,
    save_dutch_memory,
    save_dutch_progress,
    save_review,
)
from storage.paths import DUTCH_LESSONS_DIR

FailFn = Callable[[str, Exception], None]

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def pause_payload(backlog: int) -> dict:
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


def build(today_skill: str | None, *, fail: FailFn) -> tuple[dict | None, dict | None]:
    """Build the daily Dutch lesson: (delivery_payload, persist_state).

    Fully isolated — disabled via config or any failure returns (None, None) so the
    dev lesson always ships. The quiz targets YESTERDAY's words, read from memory
    here before record_dutch_lesson (in the persist step) overwrites last_words.
    """
    if not config.DUTCH_ENABLED:
        return None, None
    try:
        today = date.today()
        # Recall reports were already folded in by ingest_recall (and saved), so
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
                return pause_payload(backlog), None
        bank = dutch_wordlist.load()
        theme = dutch_wordlist.theme_for(today)
        # Recall-driven CEFR progression: once recall at the current rung clears the
        # bar, advance toward the inburgering B1 (raising the complexity the lesson
        # prompt asks for). Pure + guarded; the bumped level is on dmem, so it flows
        # into build() below and is persisted with the SR state.
        if config.DUTCH_CEFR_PROGRESSION:
            try:
                level, advanced = dutch_progress.advance_cefr(dmem, today)
                if advanced:
                    print(f"[dutch] CEFR advanced -> {level}")
            except Exception as exc:
                fail("dutch coach", exc)
        # Mistake-driven coach (v10 day 36): detect words the learner keeps failing
        # and, if any, let one LLM call pick today's focus. Fully guarded — any
        # failure falls back to mechanical selection so the lesson always ships.
        force_ids: list[str] = []
        directive = ""
        contrast_md = ""
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
                # Second tool: a contrast drill for STUCK words (wrong repeatedly, never
                # recalled) — re-exposure alone has a ceiling. Force both words of each
                # confusable pair into review and add a "mind the difference" section.
                pairs = dutch_coach.confusable_pairs(dmem, bank)
                if pairs:
                    contrast_md = dutch_coach.render_contrast(pairs)
                    contrast_ids = [cid for p in pairs for cid in (p["id"], p["with_id"])]
                    force_ids = contrast_ids + [i for i in force_ids if i not in contrast_ids]
                    print(f"[dutch] coach: {len(pairs)} contrast pair(s)")
            except Exception as exc:
                fail("dutch coach", exc)
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
            extra_sections=contrast_md,
        )
        dutch_mp3: str | None = str(OUTPUT_DIR / f"dutch-{today:%Y%m%d}.mp3")
        timings: list[dict] = []
        try:
            timings = asyncio.run(dutch_audio.build(dlesson, dutch_mp3))
        except Exception as exc:
            fail("dutch audio", exc)
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
                fail("dutch trainer", exc)
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
        fail("dutch build", exc)
        return None, None


def ingest_recall(inbound: dict, *, fail: FailFn) -> None:
    """Fold pending Dutch trainer recall reports into SR state BEFORE today's word
    selection so a failed word is already due. Routes to per-user files when
    multi-user is active, else the owner's single dutch_memory.json. Guarded: a
    Telegram hiccup degrades to exposure-only scheduling, never blocks the run."""
    if config.dutch_multiuser_active():
        _ingest_multiuser(inbound, fail=fail)
    elif inbound["recall"]:
        try:
            dmem = load_dutch_memory()
            applied = sum(record_dutch_recall(dmem, d, marks) for d, marks in inbound["recall"])
            if applied:
                save_dutch_memory(dmem)
            print(f"[dutch] recall: {len(inbound['recall'])} report(s), {applied} word(s) updated")
        except Exception as exc:
            fail("dutch recall", exc)


def _ingest_multiuser(inbound: dict, *, fail: FailFn) -> None:
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
            fail(f"dutch recall {chat_id}", exc)


def persist(dutch_state: dict, *, fail: FailFn) -> None:
    """Persist Dutch spaced-repetition state after the lesson shipped. Routes to the
    per-user persist when multi-user is active, else the owner's single file plus
    the cross-device progress scorecard and the cohort aggregate."""
    if config.dutch_multiuser_active():
        _persist_multiuser(dutch_state, fail=fail)
        return
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
        # localStorage (per-browser), so results submitted on the phone never show
        # on the computer. progress/<token>.json carries the server-side record to
        # the owner's devices (fetched via ?u=<token> from the DM link) —
        # token-gated, not a globally readable file. Synced once a day.
        save_dutch_progress(
            dutch_progress.build_progress(dutch_state["memory"]),
            review_token(config.TELEGRAM_CHAT_ID),
        )
        _publish_cohort([dutch_state["memory"]], fail=fail)
    except Exception as exc:
        fail("dutch persist", exc)


def _persist_multiuser(dutch_state: dict, *, fail: FailFn) -> None:
    """Record today's SHARED lesson into every learner's SR file and publish each
    learner's personal cross-day review (review/<token>.json). Generation stayed
    global (one lesson + audio); only SELECTION is per-user. Today's new words enter
    each schedule due later, so they don't appear in today's review — the review is
    genuinely the words each learner still owes. Per-user failures are isolated."""
    bank = dutch_wordlist.load()
    updated: list[dict] = []  # each learner's saved memory, for the cohort aggregate
    for chat_id in config.dutch_user_chat_ids():
        try:
            dmem = load_dutch_memory(chat_id)
            # Each learner advances on their OWN recall (generation stays global; only
            # the per-user scorecard level changes). Guarded inline with the persist.
            if config.DUTCH_CEFR_PROGRESSION:
                dutch_progress.advance_cefr(dmem)
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
            tok = review_token(chat_id)
            save_review(tok, payload)
            # Per-learner scorecard under the same token: a learner sees only their
            # own LESSEN history, fetched via ?u=<token> — never anyone else's.
            save_dutch_progress(dutch_progress.build_progress(dmem), tok)
            updated.append(dmem)
            print(f"[dutch] {chat_id}: SR updated, {len(payload['ids'])} review item(s)")
        except Exception as exc:
            fail(f"dutch persist {chat_id}", exc)
    _publish_cohort(updated, fail=fail)


def _publish_cohort(memories: list[dict], *, fail: FailFn) -> None:
    """Publish the anonymous cohort learning aggregate (Status tab, v11 day 40) under
    the OWNER's token, so it's fetched only via the owner's ?u=<token> link. Built from
    every learner's just-saved memory; in single-user mode the cohort is the owner alone.

    build_cohort stays pure and id-only (no learner identity); the hardest-words ids are
    joined to their Dutch/English text here so the published JSON is self-contained."""
    if not memories:
        return
    try:
        payload = dutch_cohort.build_cohort(memories)
        bank = {w["id"]: w for w in dutch_wordlist.load()}
        for word in payload.get("hardest_words", []):
            info = bank.get(word["id"], {})
            word["nl"] = info.get("nl", word["id"])
            word["en"] = info.get("en", "")
        save_cohort(payload, review_token(config.TELEGRAM_CHAT_ID))
    except Exception as exc:
        fail("cohort publish", exc)
