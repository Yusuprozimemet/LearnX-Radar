"""Build one run-history entry for the Status tab (v11 day 40).

Pure assembly only — a dict in, a normalized dict out, no IO. The IO (rolling
file, capped at RUN_HISTORY_KEEP_DAYS) lives in storage/state.py
(load_run_history / save_run_history), mirroring how dutch/progress.build_progress
is pure while storage.save_dutch_progress does the writing.

The entry deliberately carries NO raw exception text — only a stage's name and an
"ok" | "fail" verdict — so run_history.json is safe to render on the *public*
dashboard. Diagnostic detail still reaches the owner via the run-report DM
(main._report) and the Actions logs.
"""
from __future__ import annotations

from datetime import date


def build_entry(
    *,
    stages: dict[str, bool],
    sources: dict[str, int],
    llm: dict | None = None,
    delivery: dict[str, bool] | None = None,
    duration_s: float = 0.0,
    when: date | None = None,
) -> dict:
    """Normalize one run into a record.

    `stages` maps a stage name to whether it succeeded; it's flattened to
    "ok"/"fail" so no error text is ever persisted. `sources` is the per-source
    item count from the scrape (a source at 0 is a health flag for the page).
    `llm` is learnx.llm.breaker_state(); `delivery` maps a channel to whether it
    sent. `ok` is the run-level verdict: every recorded stage succeeded.
    """
    llm = llm or {}
    return {
        "date": (when or date.today()).isoformat(),
        "duration_s": round(float(duration_s), 1),
        "ok": all(stages.values()) if stages else True,
        "stages": {name: ("ok" if good else "fail") for name, good in stages.items()},
        "sources": {name: int(count) for name, count in sources.items()},
        "llm": {
            "nvidia_timeouts": int(llm.get("nvidia_timeouts", 0)),
            "breaker_tripped": bool(llm.get("breaker_tripped", False)),
        },
        "delivery": {name: bool(ok) for name, ok in (delivery or {}).items()},
    }
