"""dutch_memory.json : Dutch vocab spaced-repetition state (v5) + trainer IO.

Mirrors skill_memory.json: committed back by the workflow so the SR schedule and
streak survive across daily runs. Shape:
  {"version": 1, "cefr": "A2", "streak": 0, "last_run": "YYYY-MM-DD",
   "last_words": [id, ...],                 # the prior run's set — the quiz target
   "words": {id: {"introduced","reps","last_review","due",
                  "recall_right","recall_wrong"}},   # v9 day 33: trainer outcomes
   "lessons": [{"date","theme","audio","words":[id...],"summary"}],
   "recall": [{"date","reported","right":[id...],"wrong":[id...]}]}  # report log

Also holds the per-learner published files (review/, progress/) and the trainer
lesson archive (lessons/) that the Delft trainer page fetches.
"""
import hashlib
import hmac
import json
from datetime import date, timedelta

import config
from storage import paths


def _default_dutch_memory() -> dict:
    return {
        "version": 1,
        "cefr": config.DUTCH_CEFR_START,
        # When the current CEFR rung began (recall-driven progression only counts
        # reports at the present level). None until the first lesson/advance.
        "cefr_since": None,
        "streak": 0,
        "last_run": None,
        "last_words": [],
        "words": {},
        "lessons": [],
        "recall": [],
        # Multi-user review (Phase 1): ids + date of the most recent published
        # review list, so an rv_ report's positional marks map back to word ids.
        "last_review": {},
    }


def _dutch_memory_file(chat_id=None):
    """Path to a learner's Dutch SR file. The owner (or chat_id=None) keeps the
    historical unsuffixed dutch_memory.json (no migration, monkeypatchable in
    tests); every other learner gets dutch_memory_<chatid>.json beside it."""
    if chat_id is None or str(chat_id) == str(config.TELEGRAM_CHAT_ID):
        return paths.DUTCH_MEMORY_FILE
    return paths.DUTCH_DIR / f"dutch_memory_{chat_id}.json"


def load_dutch_memory(chat_id=None) -> dict:
    path = _dutch_memory_file(chat_id)
    if not path.exists():
        return _default_dutch_memory()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _default_dutch_memory()
    if not isinstance(data, dict):
        return _default_dutch_memory()
    # Backfill any missing keys so callers can rely on the full shape.
    for key, value in _default_dutch_memory().items():
        data.setdefault(key, value)
    return data


def save_dutch_memory(memory: dict, chat_id=None) -> None:
    paths.ensure_parent(_dutch_memory_file(chat_id)).write_text(
        json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def review_token(chat_id) -> str:
    """Unguessable, stable token naming a learner's published review file. HMAC of
    the chat id under REVIEW_TOKEN_SECRET, so review/<token>.json is not
    enumerable by raw chat id (plan/personalization.md: public-with-a-password)."""
    return hmac.new(
        str(config.REVIEW_TOKEN_SECRET).encode(), str(chat_id).encode(), hashlib.sha256
    ).hexdigest()[:16]


def save_review(token: str, payload: dict) -> None:
    """Publish one learner's cross-day review list (canonical \"what's due\")."""
    paths.REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    (paths.REVIEW_DIR / f"{token}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def save_dutch_progress(payload: dict, token: str) -> None:
    """Publish one learner's cross-device progress scorecard (dutch/progress.build_progress),
    named by their review_token so the trainer fetches progress/<token>.json via ?u=<token>.
    Per-learner (like save_review): a learner's scores are no longer a single global file
    that any visitor could read — each device shows only its own learner's history."""
    paths.DUTCH_PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
    (paths.DUTCH_PROGRESS_DIR / f"{token}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def save_dutch_lesson(payload: dict) -> None:
    """Persist today's trainer lesson JSON (v9 day 32). dutch_lesson.json is
    overwritten each run (the trainer page's default view); a dated copy goes to
    the lessons/ archive and index.json gains an entry, so the page's lesson list
    can reopen past days. Re-running the same day replaces that day's entry."""
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    paths.ensure_parent(paths.DUTCH_LESSON_FILE).write_text(text, encoding="utf-8")
    day = payload.get("date", "")
    if not day:
        return
    paths.DUTCH_LESSONS_DIR.mkdir(parents=True, exist_ok=True)
    (paths.DUTCH_LESSONS_DIR / f"dutch-{day}.json").write_text(text, encoding="utf-8")
    index_file = paths.DUTCH_LESSONS_DIR / "index.json"
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


def dutch_recall_adherence(
    memory: dict,
    today: date | None = None,
    *,
    window_days: int = config.DUTCH_STREAK_WINDOW_DAYS,
) -> int:
    """The adherence streak: how many recent lessons the learner actually completed,
    counted as the number of distinct recall-report lesson-dates within the trailing
    `window_days`. Replaces the old consecutive-cron-day count, which a same-day re-run
    reset to 1 and which measured the job, not the learner — so a learner reporting
    most days read as `streak: 2`. Distinct dates make it robust to batched reports."""
    today = today or date.today()
    start = (today - timedelta(days=window_days)).isoformat()
    dates = {
        r.get("date")
        for r in memory.get("recall", [])
        if r.get("date") and r["date"] >= start
    }
    return len(dates)


def dutch_unsubmitted_streak(memory: dict) -> int:
    """How many of the most recent delivered lessons have no recall report yet.

    A lesson counts as finished once a recall report for its date exists — i.e. the
    learner practiced and saved at least one word (an all-'x' report logs nothing,
    so it doesn't count). Counting newest-first until the first finished lesson, this
    is the run of consecutive lessons the learner hasn't completed: the backlog the
    daily run uses to decide whether to pause new generation (v10 day 37)."""
    reported = {r.get("date") for r in memory.get("recall", [])}
    streak = 0
    for lesson in reversed(memory.get("lessons", [])):
        if lesson.get("date") in reported:
            break
        streak += 1
    return streak


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
    their next `due` pushed further out. The streak is recomputed as the learner's
    recent recall-report adherence (dutch_recall_adherence), not consecutive cron days.
    `last_words` is set to today's ids (the next run's quiz target), and a lessons[]
    entry is appended.
    """
    today = (when or date.today()).isoformat()
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

    memory["streak"] = dutch_recall_adherence(memory, when or date.today())
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


def record_dutch_review(
    memory: dict, date_iso: str, marks: str, when: date | None = None
) -> int:
    """Fold a personal cross-day REVIEW report into the SR state (multi-user Phase 1);
    returns how many words it applied to (0 when it can't be used).

    `marks` is positional over `memory["last_review"]["ids"]` — the exact order of the
    review list published for `date_iso` (review_token names the file; the run stores
    the order so positions map back to ids without sending them, like the dr_ loop).
    Per mark: '1' recalled -> recall_right += 1; '0' failed -> recall_wrong += 1, reps
    reset to 1, due pulled to date_iso + base interval; 'x' untrained -> untouched.
    One report per published list: the stored `reported` flag makes a re-tap a no-op."""
    last = memory.get("last_review") or {}
    if last.get("date") != date_iso or last.get("reported"):
        return 0
    words = memory.setdefault("words", {})
    right_ids: list[str] = []
    wrong_ids: list[str] = []
    for wid, mark in zip(last.get("ids", []), marks, strict=False):
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
    last["reported"] = True  # idempotent: a duplicate deep-link tap won't double-count
    log = memory.setdefault("recall", [])
    log.append({
        "date": date_iso,
        "reported": (when or date.today()).isoformat(),
        "right": right_ids,
        "wrong": wrong_ids,
        "kind": "review",
    })
    del log[: -paths.RECALL_LOG_KEEP]
    return len(right_ids) + len(wrong_ids)


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
    del log[: -paths.RECALL_LOG_KEEP]
    return len(right_ids) + len(wrong_ids)
