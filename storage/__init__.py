"""Persistent state for LearnX-Radar.

Two separate concerns, two files (both committed back by the Actions workflow
so state survives across daily runs without external storage):

- seen_skills.json  — dedup: source items already turned into lessons
- skill_memory.json — knowledge state: concepts covered, dates, depth (v2)
- last_scored.json  — this run's ranking, so the dashboard rebuilds from state (v3)
- briefs/           — full lesson brief text, linked from lessons for Perplexity Q&A
"""
from storage.state import (
    dutch_due_words,
    filter_new,
    load_brief,
    load_dutch_memory,
    load_last_scored,
    load_memory,
    load_seen,
    load_trending_history,
    mark_seen,
    previous_lesson,
    record_dutch_lesson,
    record_lesson,
    save_brief,
    save_dutch_lesson,
    save_dutch_memory,
    save_last_scored,
    save_memory,
    save_seen,
    save_trending_history,
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
    "save_dutch_lesson",
    "dutch_due_words",
    "record_dutch_lesson",
]
