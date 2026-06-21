"""Load the curated Dutch word bank and select each day's words.

The word bank (wordlist.json) is the frozen, human-reviewed source of truth. This
module only reads and selects from it — it never calls the LLM. Selection mixes new
words (never introduced) with words due for spaced-repetition review (v5 day 17).
"""
import json
import logging
import os
from datetime import date
from pathlib import Path

from storage import dutch_due_words

log = logging.getLogger(__name__)

# The word bank is per-user state: it lives in the private LearnX-Radar-state repo
# (checked out at STATE_DIR in CI). Prefer that copy; fall back to the bundled file
# for local runs where STATE_DIR is unset. Same pattern as storage/state.py.
_BUNDLED_WORDLIST = Path(__file__).parent / "wordlist.json"


def _wordlist_path() -> Path:
    state_dir = os.environ.get("STATE_DIR")
    if state_dir:
        candidate = Path(state_dir) / "wordlist.json"
        if candidate.exists():
            return candidate
    return _BUNDLED_WORDLIST


WORDLIST_FILE = _wordlist_path()

THEMES = ("everyday", "tech")


def load(path: Path | None = None) -> list[dict]:
    """Load and lightly validate the curated word bank; [] if missing/corrupt.

    Resolves STATE_DIR at call time (not import) so the private word bank is picked
    up wherever it's mounted; pass an explicit path to override (used by tests)."""
    path = Path(path) if path is not None else _wordlist_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("Dutch wordlist load failed: %s", exc)
        return []
    words = data.get("words") if isinstance(data, dict) else None
    if not isinstance(words, list):
        return []
    return [w for w in words if isinstance(w, dict) and w.get("id") and w.get("nl")]


def theme_for(day: date) -> str:
    """Alternate themes day-to-day so consecutive mornings differ.

    'tech' on even ordinals, 'everyday' on odd — a simple, reproducible rotation.
    """
    return "tech" if day.toordinal() % 2 == 0 else "everyday"


def _by_id(words: list[dict]) -> dict[str, dict]:
    return {w["id"]: w for w in words}


def select_for_today(
    words: list[dict],
    memory: dict,
    today: date,
    *,
    theme: str,
    new_count: int,
    review_max: int,
    force_review_ids=(),
) -> tuple[list[dict], list[dict]]:
    """Return (new_words, review_words) for today.

    review_words: curated entries whose id is due for review today (oldest due
    first), capped at review_max. new_words: the first `new_count` words of `theme`
    that have never been introduced (id absent from memory['words']). When the theme
    is exhausted, falls back to any never-introduced word so a lesson still ships.

    `force_review_ids` (the coach's focus words, v10 day 36) are merged into the
    review set AHEAD of the due words so they survive the cap and are guaranteed
    taught even when not strictly due. Only already-introduced ids in the bank are
    honored. Default empty -> identical selection to the mechanical lesson.
    """
    by_id = _by_id(words)
    introduced = set(memory.get("words", {}))

    forced = [wid for wid in force_review_ids if wid in by_id and wid in introduced]
    due = [wid for wid in dutch_due_words(memory, today) if wid in by_id and wid not in forced]
    review_ids = (forced + due)[:review_max]
    review_words = [by_id[wid] for wid in review_ids]

    fresh = [w for w in words if w["id"] not in introduced]
    themed = [w for w in fresh if w.get("theme") == theme]
    new_words = themed[:new_count]
    if len(new_words) < new_count:  # theme exhausted — top up from any fresh word
        seen_ids = {w["id"] for w in new_words}
        for w in fresh:
            if w["id"] not in seen_ids:
                new_words.append(w)
                seen_ids.add(w["id"])
            if len(new_words) >= new_count:
                break
    return new_words, review_words


def entries_for(words: list[dict], ids) -> list[dict]:
    """Curated entries for the given ids (skipping ids no longer in the bank)."""
    by_id = _by_id(words)
    return [by_id[i] for i in ids if i in by_id]
