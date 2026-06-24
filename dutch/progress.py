"""Derive a learner's cross-device progress scorecard from their SR memory.

The trainer page shows per-day scores from localStorage, which is per-browser — so
a lesson finished on the phone never shows up on the computer. The recall outcomes
ARE on the server though (committed every run to dutch_memory.json). This distills
that recall log into a small JSON the Pages build publishes as progress.json, so any
device can fetch it and render the full history. Synced once per day, after a run.

Pure: a memory dict in, a plain dict out. No IO, no network.
"""
from __future__ import annotations

from datetime import date, timedelta

import config


def advance_cefr(
    memory: dict,
    today: date | None = None,
    *,
    ladder: tuple[str, ...] = config.DUTCH_CEFR_LADDER,
    recall: float = config.DUTCH_CEFR_ADVANCE_RECALL,
    min_reports: int = config.DUTCH_CEFR_ADVANCE_MIN_REPORTS,
    min_words: int = config.DUTCH_CEFR_ADVANCE_MIN_WORDS,
    window_days: int = config.DUTCH_CEFR_ADVANCE_WINDOW_DAYS,
) -> tuple[str, bool]:
    """Advance the learner one CEFR rung when recall AT the current rung clears the bar.

    Returns ``(cefr, advanced)`` and, on an advance, mutates ``memory["cefr"]`` and
    stamps ``memory["cefr_since"]`` with today (so the next rung's rate is measured
    only over reports earned at it). Conservative and one rung at a time:

    - Already at the ladder top (the B1 goal) or off-ladder -> never advances.
    - Only recall reports dated on/after ``cefr_since`` and within ``window_days``
      count, so freshly-cleared progress doesn't carry into the next rung.
    - Needs both enough reports (``min_reports``) and enough attempted words
      (``min_words``) before the rate is trusted — a couple of lucky days won't
      promote — and the pooled right/total must reach ``recall``.

    Thresholds are deliberately conservative (the owner held ~86% over ~2 weeks);
    they're plain config knobs, tunable as more data accrues.
    """
    today = today or date.today()
    cur = memory.get("cefr") or ladder[0]
    if cur not in ladder or cur == ladder[-1]:
        return cur, False
    window_start = (today - timedelta(days=window_days)).isoformat()
    floor = max(window_start, memory.get("cefr_since") or "")
    reports = [r for r in memory.get("recall", []) if (r.get("date") or "") >= floor]
    attempts = sum(len(r.get("right", [])) + len(r.get("wrong", [])) for r in reports)
    rights = sum(len(r.get("right", [])) for r in reports)
    if len(reports) < min_reports or attempts < min_words:
        return cur, False
    if attempts == 0 or rights / attempts < recall:
        return cur, False
    nxt = ladder[ladder.index(cur) + 1]
    memory["cefr"] = nxt
    memory["cefr_since"] = today.isoformat()
    return nxt, True


def build_progress(memory: dict) -> dict:
    """Per-day right/wrong from the recall log plus a few headline stats. The page
    keys `days` by date and uses a day's server score whenever the local browser has
    no result for it — so previously-submitted results appear on every device."""
    days = [
        {
            "date": r.get("date", ""),
            "right": len(r.get("right", [])),
            "wrong": len(r.get("wrong", [])),
            "reported": r.get("reported", ""),
        }
        for r in memory.get("recall", [])
        if r.get("date")
    ]
    days.sort(key=lambda d: d["date"])
    return {
        "cefr": memory.get("cefr", ""),
        "streak": int(memory.get("streak", 0) or 0),
        "words_tracked": len(memory.get("words", {})),
        "days": days,
    }
