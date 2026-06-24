"""Backward-compatible facade over the split state modules.

state.py used to hold every read/write for the committed JSON. It now re-exports
the domain modules so existing `from storage.state import …` and `state.fn(…)`
call sites keep working. The real code lives in:

- storage/paths.py        — file locations and retention caps (patch here in tests)
- storage/seen.py         — seen_skills.json dedup
- storage/skills.py       — skill_memory.json + briefs/ + slugify
- storage/aliases.py      — skill_aliases.json + denylist
- storage/scored.py       — last_scored.json + trending_history.json + cohort/
- storage/run_history.py  — run_history.json (Status tab)
- storage/dutch_state.py  — dutch_memory.json + review/ + progress/ + lessons/

New code should import from those modules (or the `storage` package) directly.
Mutable path/cap constants live in storage.paths, so tests patch `paths.NAME`.
"""
import config  # noqa: F401  — re-exported so `state.config` keeps resolving in tests
from storage.aliases import (  # noqa: F401
    apply_learned_aliases,
    flatten_aliases,
    load_alias_denylist,
    load_learned_aliases,
    save_alias_denylist,
    save_learned_aliases,
)
from storage.dutch_state import (  # noqa: F401
    _default_dutch_memory,
    _dutch_interval_days,
    _dutch_memory_file,
    dutch_due_words,
    dutch_recall_adherence,
    dutch_unsubmitted_streak,
    load_dutch_memory,
    record_dutch_lesson,
    record_dutch_recall,
    record_dutch_review,
    review_token,
    save_dutch_lesson,
    save_dutch_memory,
    save_dutch_progress,
    save_review,
)

# Path + cap constants (single source of truth; patch in tests via storage.paths).
from storage.paths import (  # noqa: F401
    _DATA_DIR,
    _DIR,
    ALIAS_DENYLIST_FILE,
    BRIEFS_DIR,
    COHORT_DIR,
    DUTCH_LESSON_FILE,
    DUTCH_LESSONS_DIR,
    DUTCH_MEMORY_FILE,
    DUTCH_PROGRESS_DIR,
    HISTORY_FILE,
    HISTORY_KEEP_DAYS,
    LAST_SCORED_FILE,
    LAST_SCORED_KEEP,
    LEARNED_ALIASES_FILE,
    MAX_SEEN,
    MEMORY_FILE,
    RECALL_LOG_KEEP,
    REVIEW_DIR,
    RUN_HISTORY_FILE,
    RUN_HISTORY_KEEP_DAYS,
    SEEN_FILE,
    SEEN_TTL_DAYS,
)
from storage.run_history import (  # noqa: F401
    build_entry,
    load_run_history,
    save_run_history,
)
from storage.scored import (  # noqa: F401
    load_last_scored,
    load_trending_history,
    save_cohort,
    save_last_scored,
    save_trending_history,
)
from storage.seen import (  # noqa: F401
    _seen_cutoff,
    filter_new,
    load_seen,
    mark_seen,
    save_seen,
)
from storage.skills import (  # noqa: F401
    _existing_skill_key,
    _norm_skill_key,
    load_brief,
    load_memory,
    previous_lesson,
    record_lesson,
    record_lesson_rating,
    save_brief,
    save_memory,
    skill_entry,
    slugify,
)
