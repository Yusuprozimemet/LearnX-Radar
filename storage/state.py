"""Read/write the two state files. Pure I/O — no scoring or LLM logic here.

Mirrors the Daily-CronJob seen.json pattern (load -> filter_new -> save), and
adds the v2 knowledge-state file skill_memory.json. The committed JSON is the
source of truth; these helpers degrade gracefully if a file is missing or
corrupt so a single bad write never wedges the daily run.
"""
import json
import re
from datetime import date, timedelta
from pathlib import Path

_DIR = Path(__file__).parent
SEEN_FILE = _DIR / "seen_skills.json"
MEMORY_FILE = _DIR / "skill_memory.json"
LAST_SCORED_FILE = _DIR / "last_scored.json"  # v3: this run's ranking for the dashboard
# v3: per-day rankings, so the dashboard date-picker can replay any day
HISTORY_FILE = _DIR / "trending_history.json"
BRIEFS_DIR = _DIR.parent / "briefs"  # committed briefs, linked from lessons for Perplexity Q&A

LAST_SCORED_KEEP = 20  # cap the persisted ranking; the dashboard only shows a top slice
HISTORY_KEEP_DAYS = 60  # cap the per-day archive so the embedded page payload stays bounded

MAX_SEEN = 5000  # cap so the dedup file doesn't grow forever
SEEN_TTL_DAYS = 14  # a sighting expires after this many days; see the seen_skills section


def slugify(text: str) -> str:
    """Filesystem/URL-safe slug for a skill name (e.g. 'Kafka consumer groups'
    -> 'kafka-consumer-groups'). Shared by brief and audio filenames so each
    lesson gets a unique, collision-free name even when several land the same day."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "lesson"


# --- seen_skills.json : dedup of source items already processed --------------
#
# Maps item-id -> ISO date last seen. The window (SEEN_TTL_DAYS) matters because
# the trend sources use time-stable IDs — a repo (gh:owner/repo), a hiring-thread
# comment (hn:id), a tag-week (so:tag:week) reappear run after run. Without a
# window they'd be suppressed forever after the first sighting, starving the
# ranking down to dev.to alone. Expiring a sighting lets a still-trending repo or
# still-hot tag re-enter as fresh demand signal. Re-teaching the same *skill* is a
# separate concern handled by gap_scorer novelty, so this window can be short.

def _seen_cutoff() -> str:
    """The ISO date before which a sighting is considered expired."""
    return (date.today() - timedelta(days=SEEN_TTL_DAYS)).isoformat()


def load_seen() -> dict[str, str]:
    """Map of item-id -> ISO date last seen.

    Legacy list-format files (bare IDs, no dates) can't be windowed, so they're
    migrated to an empty map — a one-time reset. That's safe: novelty already
    prevents re-teaching a recently taught skill, and from the next run on every
    ID carries a date the window can act on.
    """
    if not SEEN_FILE.exists():
        return {}
    try:
        data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
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
    if len(live) > MAX_SEEN:
        newest = sorted(live.items(), key=lambda kv: kv[1], reverse=True)[:MAX_SEEN]
        live = dict(newest)
    SEEN_FILE.write_text(
        json.dumps(live, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def filter_new(items: list[dict], seen: dict[str, str]) -> list[dict]:
    """Return items not seen within the TTL window (`seen` maps id -> last-seen date)."""
    cutoff = _seen_cutoff()
    fresh = {i for i, when in seen.items() if when >= cutoff}
    return [item for item in items if item["id"] not in fresh]


# --- skill_memory.json : knowledge state (v2) --------------------------------

def load_memory() -> dict:
    if not MEMORY_FILE.exists():
        return {"version": 1, "skills": {}}
    try:
        return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "skills": {}}


def save_memory(memory: dict) -> None:
    MEMORY_FILE.write_text(
        json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --- last_scored.json : this run's ranking, so the dashboard can rebuild from
# committed state alone (no API keys) — see dashboard/ + .github/workflows/pages.yml

def _ranking_quality(scored: list[dict]) -> tuple[float, int, int]:
    """A comparable 'richness' for a ranking; higher is richer.

    Guards against a degraded re-run clobbering a good board. A same-day re-run
    often sees only fresh dev.to items (the trend sources — GitHub/HN/SO — are
    unchanged since the morning run, so dedup drops them), flattening the ranking
    to every skill at 0.5 from one source. Ranked by top score, then the number
    of distinct sources represented, then entry count — so that thin run sorts
    below the richer earlier one and is kept out.
    """
    if not scored:
        return (0.0, 0, 0)
    top = max(s.get("score", 0.0) for s in scored)
    sources = {src for s in scored for src in s.get("sources", [])}
    return (top, len(sources), len(scored))


def load_last_scored() -> dict:
    if not LAST_SCORED_FILE.exists():
        return {"today_skill": None, "scored": []}
    try:
        return json.loads(LAST_SCORED_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"today_skill": None, "scored": []}


def save_last_scored(scored: list[dict], today_skill: str | None) -> None:
    # Keep the richer ranking when re-run the same day (don't let a thin dev.to-
    # only re-run flatten the board the dashboard rebuilds from). A fresh day
    # always writes, even if thin, so the board can't get stuck on stale data.
    existing = load_last_scored()
    if existing.get("updated") == date.today().isoformat() and (
        _ranking_quality(existing.get("scored", [])) > _ranking_quality(scored)
    ):
        return
    payload = {
        "updated": date.today().isoformat(),
        "today_skill": today_skill,
        "scored": scored[:LAST_SCORED_KEEP],
    }
    LAST_SCORED_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --- trending_history.json : one ranking per day, so the dashboard can replay a
# chosen day. A re-run replaces today's entry only if it is at least as rich
# (see _ranking_quality); oldest days roll off the cap.

def load_trending_history() -> dict:
    """Return {date: {"today_skill": str|None, "scored": [...]}} or {} if missing/corrupt."""
    if not HISTORY_FILE.exists():
        return {}
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_trending_history(
    scored: list[dict], today_skill: str | None, when: date | None = None
) -> None:
    """Record this run's ranking under its date, trimming to HISTORY_KEEP_DAYS."""
    when = when or date.today()
    history = load_trending_history()
    key = when.isoformat()
    prior = history.get(key)
    if prior and _ranking_quality(prior.get("scored", [])) > _ranking_quality(scored):
        return  # a thinner same-day re-run shouldn't overwrite a richer one
    history[key] = {
        "today_skill": today_skill,
        "scored": scored[:LAST_SCORED_KEEP],
    }
    for stale in sorted(history, reverse=True)[HISTORY_KEEP_DAYS:]:
        del history[stale]
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def record_lesson(
    memory: dict,
    skill: str,
    *,
    title: str,
    difficulty: str,
    summary: str = "",
    audio: str = "",
    brief: str = "",
) -> dict:
    """Update the knowledge state after a lesson on `skill` is delivered.

    Tracks times taught, last date, difficulty, a one-line summary, the MP3
    filename, and the brief filename so gap_scorer can space-repeat (v2),
    brief_writer can bridge to related lessons, the dashboard archive (v3) can
    list them, and each lesson can link to the full brief for Perplexity Q&A.
    """
    skills = memory.setdefault("skills", {})
    entry = skills.setdefault(
        skill, {"times_taught": 0, "first_taught": None, "lessons": []}
    )
    today = date.today().isoformat()
    entry["times_taught"] += 1
    entry["first_taught"] = entry["first_taught"] or today
    entry["last_taught"] = today
    entry["summary"] = summary or entry.get("summary", "")
    entry["lessons"].append(
        {
            "date": today,
            "title": title,
            "difficulty": difficulty,
            "summary": summary,
            "audio": audio,
            "brief": brief,
        }
    )
    return memory


def previous_lesson(memory: dict) -> dict | None:
    """The most recently taught lesson across all skills, or None if none yet.

    Used for the recall quiz (v4): real retrieval practice tests a *prior* lesson.
    Called before today's `record_lesson`, so the latest stored entry is genuinely
    the previous lesson. Returns the lesson dict plus its owning `skill`.
    """
    best: dict | None = None
    for skill, data in memory.get("skills", {}).items():
        for lesson in data.get("lessons", []):
            if best is None or lesson.get("date", "") > best.get("date", ""):
                best = {**lesson, "skill": skill}
    return best


# --- briefs/ : full lesson brief text, linked from lessons for Perplexity Q&A ----------

def save_brief(skill: str, brief_md: str, when: date | None = None) -> str:
    """Write the full brief to briefs/<date>-<slug>.md; return the filename."""
    when = when or date.today()
    filename = f"{when:%Y%m%d}-{slugify(skill)}.md"
    BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    (BRIEFS_DIR / filename).write_text(brief_md, encoding="utf-8")
    return filename


def load_brief(filename: str) -> str:
    """Return a saved brief's text, or '' if missing/unreadable."""
    if not filename:
        return ""
    try:
        return (BRIEFS_DIR / filename).read_text(encoding="utf-8")
    except OSError:
        return ""
