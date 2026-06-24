"""seen_skills.json : dedup of source items already processed.

Maps item-id -> ISO date last seen. The window (SEEN_TTL_DAYS) matters because
the trend sources use time-stable IDs — a repo (gh:owner/repo), a hiring-thread
comment (hn:id), a tag-week (so:tag:week) reappear run after run. Without a
window they'd be suppressed forever after the first sighting, starving the
ranking down to dev.to alone. Expiring a sighting lets a still-trending repo or
still-hot tag re-enter as fresh demand signal. Re-teaching the same *skill* is a
separate concern handled by gap_scorer novelty, so this window can be short.

Mirrors the Daily-CronJob seen.json pattern (load -> filter_new -> save).
"""
import json
from datetime import date, timedelta

from storage import paths


def _seen_cutoff() -> str:
    """The ISO date before which a sighting is considered expired."""
    return (date.today() - timedelta(days=paths.SEEN_TTL_DAYS)).isoformat()


def load_seen() -> dict[str, str]:
    """Map of item-id -> ISO date last seen.

    Legacy list-format files (bare IDs, no dates) can't be windowed, so they're
    migrated to an empty map — a one-time reset. That's safe: novelty already
    prevents re-teaching a recently taught skill, and from the next run on every
    ID carries a date the window can act on.
    """
    if not paths.SEEN_FILE.exists():
        return {}
    try:
        data = json.loads(paths.SEEN_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def mark_seen(seen: dict[str, str], ids, when: str | None = None) -> None:
    """Stamp each id in `ids` as seen on `when` (default today), mutating `seen`.

    Only newly processed items are stamped; items filtered out as still-seen keep
    their original date, so the window runs from first sighting — a repo that
    keeps trending re-surfaces every SEEN_TTL_DAYS instead of being locked out.
    """
    when = when or date.today().isoformat()
    for i in ids:
        seen[i] = when


def save_seen(seen: dict[str, str]) -> None:
    """Persist, dropping entries past the TTL and capping at the newest MAX_SEEN."""
    cutoff = _seen_cutoff()
    live = {i: w for i, w in seen.items() if w >= cutoff}
    if len(live) > paths.MAX_SEEN:
        newest = sorted(live.items(), key=lambda kv: kv[1], reverse=True)[: paths.MAX_SEEN]
        live = dict(newest)
    paths.SEEN_FILE.write_text(
        json.dumps(live, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def filter_new(items: list[dict], seen: dict[str, str]) -> list[dict]:
    """Return items not seen within the TTL window (`seen` maps id -> last-seen date)."""
    cutoff = _seen_cutoff()
    fresh = {i for i, when in seen.items() if when >= cutoff}
    return [item for item in items if item["id"] not in fresh]
