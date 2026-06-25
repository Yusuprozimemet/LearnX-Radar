"""Per-run pipeline health for the Status tab (v11 day 40): build + rolling IO.

build_entry is pure assembly — a dict in, a normalized dict out. load/save keep
one entry per day, keyed by date, capped at RUN_HISTORY_KEEP_DAYS (mirroring
storage.scored.save_trending_history). dutch/progress.build_progress is pure the
same way, with storage.dutch_state.save_dutch_progress doing its writing.

The entry deliberately carries NO raw exception text — only a stage's name and an
"ok" | "fail" verdict — so run_history.json is safe to render on the *public*
dashboard. Diagnostic detail still reaches the owner via the run-report DM
(main._report) and the Actions logs.
"""
from __future__ import annotations

import json
from datetime import date

from storage import paths


def build_entry(
    *,
    stages: dict[str, bool],
    sources: dict[str, int],
    llm: dict | None = None,
    delivery: dict[str, bool] | None = None,
    duration_s: float = 0.0,
    timings: dict[str, float] | None = None,
    when: date | None = None,
) -> dict:
    """Normalize one run into a record.

    `stages` maps a stage name to whether it succeeded; it's flattened to
    "ok"/"fail" so no error text is ever persisted. `sources` is the per-source
    item count from the scrape (a source at 0 is a health flag for the page).
    `llm` is learnx.llm.breaker_state(); `delivery` maps a channel to whether it
    sent. `timings` maps a stage name to its wall-clock seconds (the heavy
    stages only) so the page can show where a run spends its time, not just the
    total. `ok` is the run-level verdict: every recorded stage succeeded.
    """
    llm = llm or {}
    return {
        "date": (when or date.today()).isoformat(),
        "duration_s": round(float(duration_s), 1),
        "ok": all(stages.values()) if stages else True,
        "stages": {name: ("ok" if good else "fail") for name, good in stages.items()},
        "sources": {name: int(count) for name, count in sources.items()},
        "timings": {name: round(float(s), 1) for name, s in (timings or {}).items()},
        "llm": {
            "nvidia_timeouts": int(llm.get("nvidia_timeouts", 0)),
            "breaker_tripped": bool(llm.get("breaker_tripped", False)),
        },
        "delivery": {name: bool(ok) for name, ok in (delivery or {}).items()},
    }


def load_run_history() -> dict:
    """Return {date: run-entry} or {} if missing/corrupt."""
    if not paths.RUN_HISTORY_FILE.exists():
        return {}
    try:
        data = json.loads(paths.RUN_HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_run_history(entry: dict, when: date | None = None) -> None:
    """Record one run entry under its date, trimming to RUN_HISTORY_KEEP_DAYS."""
    when = when or date.today()
    history = load_run_history()
    history[entry.get("date") or when.isoformat()] = entry
    for stale in sorted(history, reverse=True)[paths.RUN_HISTORY_KEEP_DAYS:]:
        del history[stale]
    paths.ensure_parent(paths.RUN_HISTORY_FILE).write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )
