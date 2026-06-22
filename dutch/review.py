"""Build a learner's personal cross-day review from the shared lesson archive.

Phase 1 personalization: generation is GLOBAL (one lesson + audio per day, shared
by everyone) while SELECTION is per-user. Each allowlisted learner keeps their own
dutch_memory_<chatid>.json spaced-repetition state; this distills the words that are
DUE for that learner today and pairs each with a real example sentence + audio span
pulled from the day it was taught (the lessons/ archive) — so the trainer page can
drill them with no extra LLM or TTS. The published review/<token>.json is the
canonical "what's due"; the page reconciles its localStorage cache to it.

Pure composition + file reads — no LLM, no network. See plan/personalization.md.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from dutch import cloze
from storage.state import dutch_due_words


def _archive_drills(lessons_dir: Path) -> dict[str, dict]:
    """Map a word's match-form (lowercased) -> a drillable example from the archive.

    Scans every archived trainer lesson (oldest first, so a newer day overwrites an
    older example) and indexes each audio SEGMENT under the report-word forms it
    contains. A segment already carries {nl, en, start_ms, end_ms}, so the page gets
    a real sentence to blank plus the audio span to replay it. Missing/corrupt
    archive files are skipped — a word with no example still ships as gloss-only.
    """
    out: dict[str, dict] = {}
    if not lessons_dir.exists():
        return out
    for f in sorted(lessons_dir.glob("dutch-*.json")):
        try:
            lesson = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        audio_url = lesson.get("audio_url", "")
        forms = [
            (w.get("form") or "").lower()
            for w in (lesson.get("report") or {}).get("words", [])
            if w.get("form")
        ]
        for seg in lesson.get("segments") or []:
            nl_low = (seg.get("nl") or "").lower()
            for form in forms:
                if form and form in nl_low:
                    out[form] = {
                        "sentence_nl": seg.get("nl", ""),
                        "sentence_en": seg.get("en", ""),
                        "audio_url": audio_url,
                        "start_ms": seg.get("start_ms", 0),
                        "end_ms": seg.get("end_ms", 0),
                    }
    return out


def build(
    memory: dict,
    lessons_dir: Path,
    bank: list[dict],
    *,
    today: date | None = None,
    max_items: int = 12,
) -> dict:
    """A learner's review payload: the words due today, gloss from the frozen bank,
    each enriched with an example sentence + audio span when the archive has one.

    `ids` is the report contract — an rv_<date>_<marks> deep link reports one mark per
    position over THIS order, so the next run maps positions back to ids (the run
    stores it as memory["last_review"]). Today's freshly taught words aren't due yet,
    so they don't appear here; this is genuine cross-day review.
    """
    today = today or date.today()
    by_id = {w["id"]: w for w in bank}
    drills = _archive_drills(lessons_dir)
    items: list[dict] = []
    for wid in dutch_due_words(memory, today):
        word = by_id.get(wid)
        if word is None:  # id no longer in the frozen bank
            continue
        form = cloze.match_form(word.get("nl", ""))
        item = {
            "id": wid,
            "nl": word.get("nl", ""),
            "en": word.get("en", ""),
            "form": form,
        }
        item.update(drills.get(form.lower(), {}))
        items.append(item)
        if len(items) >= max_items:
            break
    return {
        "generated": today.isoformat(),
        "items": items,
        "ids": [it["id"] for it in items],
    }
