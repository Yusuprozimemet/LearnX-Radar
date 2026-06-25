"""Dashboard ranking state: last_scored.json + trending_history.json + cohort/.

last_scored.json is this run's ranking; trending_history.json keeps one ranking
per day so the dashboard date-picker can replay any day. Both let the Pages build
rebuild from committed state alone (no API keys) — see dashboard/ and
.github/workflows/pages.yml. save_cohort publishes the anonymous learning
aggregate next to them. Per-run pipeline health lives in storage/run_history.py.
"""
import json
from datetime import date

from storage import paths


def load_last_scored() -> dict:
    if not paths.LAST_SCORED_FILE.exists():
        return {"today_skill": None, "scored": []}
    try:
        return json.loads(paths.LAST_SCORED_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"today_skill": None, "scored": []}


def save_last_scored(scored: list[dict], today_skill: str | None) -> None:
    payload = {
        "updated": date.today().isoformat(),
        "today_skill": today_skill,
        "scored": scored[: paths.LAST_SCORED_KEEP],
    }
    paths.ensure_parent(paths.LAST_SCORED_FILE).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_trending_history() -> dict:
    """Return {date: {"today_skill": str|None, "scored": [...]}} or {} if missing/corrupt."""
    if not paths.HISTORY_FILE.exists():
        return {}
    try:
        data = json.loads(paths.HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_trending_history(
    scored: list[dict], today_skill: str | None, when: date | None = None
) -> None:
    """Record this run's ranking under its date, trimming to HISTORY_KEEP_DAYS."""
    when = when or date.today()
    history = load_trending_history()
    history[when.isoformat()] = {
        "today_skill": today_skill,
        "scored": scored[: paths.LAST_SCORED_KEEP],
    }
    for stale in sorted(history, reverse=True)[paths.HISTORY_KEEP_DAYS:]:
        del history[stale]
    paths.ensure_parent(paths.HISTORY_FILE).write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def save_cohort(payload: dict, token: str) -> None:
    """Publish the anonymous cohort learning aggregate (dutch/cohort.build_cohort),
    named by the owner's review_token so the Status tab fetches cohort/<token>.json
    via ?u=<token> — owner-only, never a guessable global file."""
    paths.COHORT_DIR.mkdir(parents=True, exist_ok=True)
    (paths.COHORT_DIR / f"{token}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
