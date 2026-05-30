"""Read/write the two state files. Pure I/O — no scoring or LLM logic here.

Mirrors the Daily-CronJob seen.json pattern (load -> filter_new -> save), and
adds the v2 knowledge-state file skill_memory.json. The committed JSON is the
source of truth; these helpers degrade gracefully if a file is missing or
corrupt so a single bad write never wedges the daily run.
"""
import json
from datetime import date
from pathlib import Path

_DIR = Path(__file__).parent
SEEN_FILE = _DIR / "seen_skills.json"
MEMORY_FILE = _DIR / "skill_memory.json"
LAST_SCORED_FILE = _DIR / "last_scored.json"  # v3: this run's ranking for the dashboard

LAST_SCORED_KEEP = 20  # cap the persisted ranking; the dashboard only shows a top slice

MAX_SEEN = 5000  # cap so the dedup file doesn't grow forever


# --- seen_skills.json : dedup of source items already taught -----------------

def load_seen() -> set[str]:
    if not SEEN_FILE.exists():
        return set()
    try:
        return set(json.loads(SEEN_FILE.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return set()


def save_seen(seen: set[str]) -> None:
    trimmed = list(seen)[-MAX_SEEN:]
    SEEN_FILE.write_text(json.dumps(trimmed, indent=0), encoding="utf-8")


def filter_new(items: list[dict], seen: set[str]) -> list[dict]:
    """Return only items whose 'id' isn't already in seen."""
    return [item for item in items if item["id"] not in seen]


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


def record_lesson(
    memory: dict,
    skill: str,
    *,
    title: str,
    difficulty: str,
    summary: str = "",
    audio: str = "",
) -> dict:
    """Update the knowledge state after a lesson on `skill` is delivered.

    Tracks times taught, last date, difficulty, a one-line summary, and the MP3
    filename so gap_scorer can space-repeat (v2), brief_writer can bridge to
    related prior lessons, and the dashboard archive (v3) can link the audio.
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
        }
    )
    return memory
