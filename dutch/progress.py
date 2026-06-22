"""Derive a learner's cross-device progress scorecard from their SR memory.

The trainer page shows per-day scores from localStorage, which is per-browser — so
a lesson finished on the phone never shows up on the computer. The recall outcomes
ARE on the server though (committed every run to dutch_memory.json). This distills
that recall log into a small JSON the Pages build publishes as progress.json, so any
device can fetch it and render the full history. Synced once per day, after a run.

Pure: a memory dict in, a plain dict out. No IO, no network.
"""
from __future__ import annotations


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
