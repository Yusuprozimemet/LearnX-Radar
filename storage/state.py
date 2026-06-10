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

import config

_DIR = Path(__file__).parent
SEEN_FILE = _DIR / "seen_skills.json"
MEMORY_FILE = _DIR / "skill_memory.json"
LAST_SCORED_FILE = _DIR / "last_scored.json"  # v3: this run's ranking for the dashboard
# v3: per-day rankings, so the dashboard date-picker can replay any day
HISTORY_FILE = _DIR / "trending_history.json"
BRIEFS_DIR = _DIR.parent / "briefs"  # committed briefs, linked from lessons for Perplexity Q&A
DUTCH_MEMORY_FILE = _DIR / "dutch_memory.json"  # v5: Dutch vocab spaced-repetition state
# v9 day 32: today's full Dutch lesson (text + cloze + audio seek map) for the
# Delft trainer page — committed by the workflow, copied to Pages, fetched by JS.
DUTCH_LESSON_FILE = _DIR / "dutch_lesson.json"
# Lesson archive: a dated copy of every trainer lesson plus an index.json manifest,
# so the trainer page can reopen any past day (Duolingo-style lesson nodes). Grows
# from the day this shipped — earlier lessons were overwritten and exist as audio only.
DUTCH_LESSONS_DIR = _DIR / "lessons"

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

def load_last_scored() -> dict:
    if not LAST_SCORED_FILE.exists():
        return {"today_skill": None, "scored": []}
    try:
        return json.loads(LAST_SCORED_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"today_skill": None, "scored": []}


def save_last_scored(scored: list[dict], today_skill: str | None) -> None:
    payload = {
        "updated": date.today().isoformat(),
        "today_skill": today_skill,
        "scored": scored[:LAST_SCORED_KEEP],
    }
    LAST_SCORED_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --- trending_history.json : one ranking per day, so the dashboard can replay a
# chosen day. Overwrites today's entry on re-run; oldest days roll off the cap.

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
    history[when.isoformat()] = {
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


# --- dutch_memory.json : Dutch vocab spaced-repetition state (v5) -------------
#
# Mirrors skill_memory.json: committed back by the workflow so the SR schedule and
# streak survive across daily runs. Shape:
#   {"version": 1, "cefr": "A2", "streak": 0, "last_run": "YYYY-MM-DD",
#    "last_words": [id, ...],                 # the prior run's set — the quiz target
#    "words": {id: {"introduced","reps","last_review","due",
#                   "recall_right","recall_wrong"}},   # v9 day 33: trainer outcomes
#    "lessons": [{"date","theme","audio","words":[id...],"summary"}],
#    "recall": [{"date","reported","right":[id...],"wrong":[id...]}]}  # report log

RECALL_LOG_KEEP = 90  # reports kept; the dashboard's rolling window only needs 30


def _default_dutch_memory() -> dict:
    return {
        "version": 1,
        "cefr": config.DUTCH_CEFR_START,
        "streak": 0,
        "last_run": None,
        "last_words": [],
        "words": {},
        "lessons": [],
        "recall": [],
    }


def load_dutch_memory() -> dict:
    if not DUTCH_MEMORY_FILE.exists():
        return _default_dutch_memory()
    try:
        data = json.loads(DUTCH_MEMORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _default_dutch_memory()
    if not isinstance(data, dict):
        return _default_dutch_memory()
    # Backfill any missing keys so callers can rely on the full shape.
    for key, value in _default_dutch_memory().items():
        data.setdefault(key, value)
    return data


def save_dutch_memory(memory: dict) -> None:
    DUTCH_MEMORY_FILE.write_text(
        json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def save_dutch_lesson(payload: dict) -> None:
    """Persist today's trainer lesson JSON (v9 day 32). dutch_lesson.json is
    overwritten each run (the trainer page's default view); a dated copy goes to
    the lessons/ archive and index.json gains an entry, so the page's lesson list
    can reopen past days. Re-running the same day replaces that day's entry."""
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    DUTCH_LESSON_FILE.write_text(text, encoding="utf-8")
    day = payload.get("date", "")
    if not day:
        return
    DUTCH_LESSONS_DIR.mkdir(exist_ok=True)
    (DUTCH_LESSONS_DIR / f"dutch-{day}.json").write_text(text, encoding="utf-8")
    index_file = DUTCH_LESSONS_DIR / "index.json"
    try:
        index = json.loads(index_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        index = {}
    lessons = [e for e in index.get("lessons", []) if e.get("date") != day]
    lessons.append(
        {
            "date": day,
            "theme": payload.get("theme", ""),
            "cefr": payload.get("cefr", ""),
        }
    )
    lessons.sort(key=lambda e: e.get("date", ""))
    index_file.write_text(
        json.dumps({"lessons": lessons}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def dutch_due_words(memory: dict, today: date | None = None) -> list[str]:
    """Ids whose review is due on/before `today`, oldest due date first."""
    today_iso = (today or date.today()).isoformat()
    due = [
        (wid, entry.get("due", ""))
        for wid, entry in memory.get("words", {}).items()
        if entry.get("due", "") and entry["due"] <= today_iso
    ]
    due.sort(key=lambda pair: pair[1])
    return [wid for wid, _ in due]


def _dutch_interval_days(reps: int) -> int:
    """Spacing interval (days) after `reps` exposures: widens with each rep."""
    base = config.DUTCH_SR_BASE_INTERVAL_DAYS
    factor = config.DUTCH_SR_SPACING_FACTOR
    return max(1, round(base * (factor ** max(0, reps - 1))))


def record_dutch_lesson(
    memory: dict,
    *,
    word_ids,
    theme: str,
    audio: str = "",
    summary: str = "",
    when: date | None = None,
) -> dict:
    """Update Dutch SR state after a lesson covering `word_ids` is delivered.

    New words start at reps=1; re-served (review) words have their reps bumped and
    their next `due` pushed further out. Streak increments on a consecutive day and
    resets after a gap. `last_words` is set to today's ids (the next run's quiz
    target), and a lessons[] entry is appended.
    """
    today = (when or date.today()).isoformat()
    yesterday = ((when or date.today()) - timedelta(days=1)).isoformat()
    words = memory.setdefault("words", {})
    ids = list(word_ids)

    for wid in ids:
        entry = words.get(wid)
        if entry is None:
            reps = 1
            entry = {"introduced": today, "reps": reps, "last_review": today}
        else:
            reps = int(entry.get("reps", 1)) + 1
            entry["reps"] = reps
            entry["last_review"] = today
            entry.setdefault("introduced", today)
        due = (date.fromisoformat(today) + timedelta(days=_dutch_interval_days(reps))).isoformat()
        entry["due"] = due
        words[wid] = entry

    last_run = memory.get("last_run")
    if last_run == yesterday:
        memory["streak"] = int(memory.get("streak", 0)) + 1
    else:
        memory["streak"] = 1
    memory["last_run"] = today
    memory["last_words"] = ids
    memory.setdefault("lessons", []).append(
        {
            "date": today,
            "theme": theme,
            "audio": audio,
            "words": ids,
            "summary": summary,
        }
    )
    return memory


def record_dutch_recall(
    memory: dict, date_iso: str, marks: str, when: date | None = None
) -> int:
    """Fold one trainer recall report into the SR state (v9 day 33); returns the
    number of words it applied to (0 when the report can't be used).

    `marks` is positional over the words of the lesson dated `date_iso` (the same
    new+review order record_dutch_lesson stored). Per mark:
      '1' (recalled)   -> recall_right += 1. Scheduling unchanged — the exposure
                          bump at delivery already widened the interval, which is
                          exactly "behaves as today" for a remembered word.
      '0' (failed)     -> recall_wrong += 1, reps reset to 1, due = lesson date +
                          base interval — the word reappears like a forgotten card.
      'x' (not trained)-> untouched: exposure-based scheduling stays the fallback,
                          so skipping the trainer never punishes.
    One report per lesson date — the FIRST wins (a duplicate tap on the deep link
    must not double-count the recall counters).
    """
    lesson = next(
        (les for les in reversed(memory.get("lessons", [])) if les.get("date") == date_iso),
        None,
    )
    if lesson is None:
        return 0
    if any(r.get("date") == date_iso for r in memory.get("recall", [])):
        return 0  # already folded in
    words = memory.setdefault("words", {})
    right_ids: list[str] = []
    wrong_ids: list[str] = []
    # strict=False: a malformed report (marks shorter/longer than the lesson's
    # words) degrades to applying the overlap instead of crashing the run.
    for wid, mark in zip(lesson.get("words", []), marks, strict=False):
        entry = words.get(wid)
        if entry is None or mark == "x":
            continue
        if mark == "1":
            entry["recall_right"] = int(entry.get("recall_right", 0)) + 1
            right_ids.append(wid)
        else:
            entry["recall_wrong"] = int(entry.get("recall_wrong", 0)) + 1
            entry["reps"] = 1
            entry["due"] = (
                date.fromisoformat(date_iso) + timedelta(days=_dutch_interval_days(1))
            ).isoformat()
            wrong_ids.append(wid)
    if not right_ids and not wrong_ids:
        return 0
    log = memory.setdefault("recall", [])
    log.append(
        {
            "date": date_iso,
            "reported": (when or date.today()).isoformat(),
            "right": right_ids,
            "wrong": wrong_ids,
        }
    )
    del log[:-RECALL_LOG_KEEP]
    return len(right_ids) + len(wrong_ids)
