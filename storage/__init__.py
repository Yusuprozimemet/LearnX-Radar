"""Persistent state for LearnX-Radar.

Two separate concerns, two files (both committed back by the Actions workflow
so state survives across daily runs without external storage):

- seen_skills.json  — dedup: source items already turned into lessons
- skill_memory.json — knowledge state: concepts covered, dates, depth (v2)
- last_scored.json  — this run's ranking, so the dashboard rebuilds from state (v3)
- briefs/           — full lesson brief text, linked from lessons for Perplexity Q&A
"""
from storage import run_history
from storage.aliases import (
    apply_learned_aliases,
    flatten_aliases,
    load_alias_denylist,
    load_learned_aliases,
    save_alias_denylist,
    save_learned_aliases,
)
from storage.dutch_state import (
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
from storage.run_history import load_run_history, save_run_history
from storage.scored import (
    load_last_scored,
    load_trending_history,
    save_cohort,
    save_last_scored,
    save_trending_history,
)
from storage.seen import filter_new, load_seen, mark_seen, save_seen
from storage.skills import (
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

__all__ = [
    "load_seen",
    "save_seen",
    "mark_seen",
    "filter_new",
    "load_memory",
    "save_memory",
    "record_lesson",
    "record_lesson_rating",
    "skill_entry",
    "previous_lesson",
    "load_last_scored",
    "save_last_scored",
    "load_trending_history",
    "save_trending_history",
    "save_brief",
    "load_brief",
    "slugify",
    "load_dutch_memory",
    "save_dutch_memory",
    "save_review",
    "review_token",
    "save_dutch_lesson",
    "save_dutch_progress",
    "dutch_due_words",
    "dutch_recall_adherence",
    "dutch_unsubmitted_streak",
    "record_dutch_lesson",
    "record_dutch_recall",
    "record_dutch_review",
    "load_learned_aliases",
    "save_learned_aliases",
    "apply_learned_aliases",
    "flatten_aliases",
    "load_alias_denylist",
    "save_alias_denylist",
    "load_run_history",
    "save_run_history",
    "save_cohort",
    "run_history",
]
