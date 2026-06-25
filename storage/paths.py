"""File locations and retention caps for all persisted state — one place.

Split out of storage/state.py so the domain modules (seen, skills, aliases,
scored, dutch_state, run_history) share a single source of truth for paths and
can be patched from one place in tests. Every domain function reads these as
`paths.NAME` so a test that rebinds `paths.DUTCH_MEMORY_FILE` is seen by the
function at call time, regardless of which module the function lives in.

The committed JSON is the source of truth; the readers degrade gracefully if a
file is missing or corrupt so a single bad write never wedges the daily run.
"""
import os
from pathlib import Path

_DIR = Path(__file__).parent  # where this package's code lives (always in the public repo)
# Where per-user state JSON/MD lives. Defaults to this package dir so local runs and
# tests are unchanged, but CI points STATE_DIR at a checkout of the *private* state
# repo (LearnX-Radar-state) so personal data never lands in the public repo. Briefs
# stay public (they're fetched by raw URL), so BRIEFS_DIR keeps tracking _DIR.
_DATA_DIR = Path(os.environ.get("STATE_DIR", _DIR))
# State is grouped by track so the private repo is navigable at a glance: radar/
# holds the English dev-skill radar, dutch/ holds the inburgering track. See the
# state repo's README. Writers go through ensure_parent() so these subdirs are
# created on first write (day-one / a fresh checkout has neither yet).
RADAR_DIR = _DATA_DIR / "radar"
DUTCH_DIR = _DATA_DIR / "dutch"

SEEN_FILE = RADAR_DIR / "seen_skills.json"
MEMORY_FILE = RADAR_DIR / "skill_memory.json"
LAST_SCORED_FILE = RADAR_DIR / "last_scored.json"  # v3: this run's ranking for the dashboard
# v3: per-day rankings, so the dashboard date-picker can replay any day
HISTORY_FILE = RADAR_DIR / "trending_history.json"
BRIEFS_DIR = _DIR.parent / "briefs"  # committed briefs, linked from lessons for Perplexity Q&A
DUTCH_MEMORY_FILE = DUTCH_DIR / "dutch_memory.json"  # v5: Dutch vocab spaced-repetition state
# v7 day26 vectordb: skill-name aliases LEARNED autonomously by alias_curator
# (embeddings shortlist -> LLM judge), merged into config.SKILL_ALIASES at startup
# so the scorer/extractor collapse the same variants the hand-written map does.
LEARNED_ALIASES_FILE = RADAR_DIR / "skill_aliases.json"
# Pairs a human reverted ("keep separate"); the curator skips them forever so the
# weekly loop can't re-merge a decision you've already overruled.
ALIAS_DENYLIST_FILE = RADAR_DIR / "skill_aliases_denylist.json"
# Audit trail of every autonomous alias decision (merge AND keep-separate). Lives
# beside the alias files it explains; written by scripts.curate_aliases.
ALIAS_LOG_FILE = RADAR_DIR / "skill_aliases_log.md"
# v11 day 40: per-run pipeline health (stages ok/fail, source counts, LLM fallback)
# for the dashboard Status tab. One entry per day, rolling — carries no raw error
# text (see storage/run_history.py), so it's safe on the public page.
RUN_HISTORY_FILE = RADAR_DIR / "run_history.json"

# v9 day 32: today's full Dutch lesson (text + cloze + audio seek map) for the
# Delft trainer page — committed by the workflow, copied to Pages, fetched by JS.
DUTCH_LESSON_FILE = DUTCH_DIR / "dutch_lesson.json"
# Frozen, human-reviewed Dutch word bank (the lesson's source of truth). Read by
# dutch/wordlist.py, which prefers this copy and falls back to the bundled one.
DUTCH_WORDLIST_FILE = DUTCH_DIR / "wordlist.json"
# Audit trail of the mistake-driven coach's daily focus plan (dutch/coach.py).
DUTCH_COACH_LOG_FILE = DUTCH_DIR / "dutch_coach_log.md"
# Cross-device progress scorecard: per-day recall scores distilled from dutch_memory
# (see dutch/progress.py), published to Pages so a result submitted on one device
# shows on every device. The trainer's own LESSEN scores are localStorage (per-browser).
# Named by the same HMAC token as review/ (one file per learner), so a learner only
# ever sees their OWN scores — never a guessable global file readable by anyone.
DUTCH_PROGRESS_DIR = DUTCH_DIR / "progress"
# Lesson archive: a dated copy of every trainer lesson plus an index.json manifest,
# so the trainer page can reopen any past day. Grows
# from the day this shipped — earlier lessons were overwritten and exist as audio only.
DUTCH_LESSONS_DIR = DUTCH_DIR / "lessons"
# Multi-user (Phase 1): per-learner cross-day review lists, named by an HMAC token
# of the chat id (review_token). Published to Pages; the trainer page fetches
# review/<token>.json when opened with ?u=<token>. See plan/personalization.md.
REVIEW_DIR = DUTCH_DIR / "review"
# v11 day 40: anonymous multi-user learning aggregate (dutch/cohort.build_cohort),
# named by the OWNER's review_token so it's fetched only via ?u=<token> like progress/.
COHORT_DIR = DUTCH_DIR / "cohort"


def ensure_parent(path: Path) -> Path:
    """Create path's parent dir (the radar/ or dutch/ subfolder) and return path.
    Flat-file writers call this so a fresh checkout — which has neither subdir —
    doesn't fail on the first write. Dir-based stores mkdir their own dir already."""
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

LAST_SCORED_KEEP = 20  # cap the persisted ranking; the dashboard only shows a top slice
HISTORY_KEEP_DAYS = 60  # cap the per-day archive so the embedded page payload stays bounded
RUN_HISTORY_KEEP_DAYS = 60  # match the trending archive; bounds the Status heatmap

MAX_SEEN = 5000  # cap so the dedup file doesn't grow forever
SEEN_TTL_DAYS = 14  # a sighting expires after this many days; see the seen_skills section

RECALL_LOG_KEEP = 90  # Dutch recall reports kept; the dashboard's rolling window needs 30
