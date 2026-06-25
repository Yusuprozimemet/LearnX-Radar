"""skill_memory.json : knowledge state (v2) + briefs/ : full lesson brief text.

The knowledge state tracks concepts covered, dates, and depth so gap_scorer can
space-repeat. Briefs are the full lesson text, linked from each lesson for
Perplexity Q&A. `slugify` lives here because the brief and audio filenames share
it (one collision-free name per lesson, even when several land the same day).
"""
import json
import re
from datetime import date

from storage import paths


def slugify(text: str) -> str:
    """Filesystem/URL-safe slug for a skill name (e.g. 'Kafka consumer groups'
    -> 'kafka-consumer-groups'). Shared by brief and audio filenames so each
    lesson gets a unique, collision-free name even when several land the same day."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "lesson"


def load_memory() -> dict:
    if not paths.MEMORY_FILE.exists():
        return {"version": 1, "skills": {}}
    try:
        return json.loads(paths.MEMORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "skills": {}}


def save_memory(memory: dict) -> None:
    paths.ensure_parent(paths.MEMORY_FILE).write_text(
        json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _norm_skill_key(name: str) -> str:
    """Case/whitespace-fold a skill name for skill_memory lookups. Mirrors
    radar.skill_extractor._canonical's fold, minus the alias map (alias-equivalent
    variants are already merged upstream into a single display name, so only case and
    whitespace differ between days — and that difference is what split the memory)."""
    return re.sub(r"\s+", " ", str(name).strip().lower())


def _existing_skill_key(skills: dict, skill: str) -> str:
    """An existing skills key matching `skill` case-insensitively, else `skill` itself."""
    target = _norm_skill_key(skill)
    return next((k for k in skills if _norm_skill_key(k) == target), skill)


def skill_entry(memory: dict, skill: str) -> dict | None:
    """The skill_memory entry for `skill`, matched case-insensitively — the entry
    whatever case it was first stored under, or None if never taught. Used by the
    gap scorer's novelty so a case-variant surface form ('langchain' vs 'LangChain')
    doesn't read as never-taught and reset the spaced-repetition suppression."""
    skills = memory.get("skills", {})
    entry = skills.get(skill)
    if entry is not None:
        return entry
    key = _existing_skill_key(skills, skill)
    return skills.get(key) if key in skills else None


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
    # Reuse an existing entry whatever case it was first stored under, so a topic
    # recorded as "LangChain" isn't re-created as "langchain" on a later day — that
    # split is what reset novelty and re-taught the same skill 5x. See skill_entry.
    key = skill if skill in skills else _existing_skill_key(skills, skill)
    entry = skills.setdefault(
        key, {"times_taught": 0, "first_taught": None, "lessons": []}
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


def record_lesson_rating(memory: dict, date_iso: str, rating: int) -> int:
    """Stamp an owner quality rating (1–5) on the lesson(s) taught on `date_iso`;
    returns how many lesson entries it applied to (0 when no lesson has that date).

    Overwrites any prior rating for the date — unlike the Dutch recall fold-in
    (first report wins, to protect counters), a rating is an opinion, so a
    re-tap legitimately supersedes the earlier one.
    """
    applied = 0
    for data in memory.get("skills", {}).values():
        for lesson in data.get("lessons", []):
            if lesson.get("date") == date_iso:
                lesson["rating"] = int(rating)
                applied += 1
    return applied


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


def save_brief(skill: str, brief_md: str, when: date | None = None) -> str:
    """Write the full brief to briefs/<date>-<slug>.md; return the filename."""
    when = when or date.today()
    filename = f"{when:%Y%m%d}-{slugify(skill)}.md"
    paths.BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    (paths.BRIEFS_DIR / filename).write_text(brief_md, encoding="utf-8")
    return filename


def load_brief(filename: str) -> str:
    """Return a saved brief's text, or '' if missing/unreadable."""
    if not filename:
        return ""
    try:
        return (paths.BRIEFS_DIR / filename).read_text(encoding="utf-8")
    except OSError:
        return ""
