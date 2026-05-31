"""Persistent state for LearnX-Radar.

Two separate concerns, two files (both committed back by the Actions workflow
so state survives across daily runs without external storage):

- seen_skills.json  — dedup: source items already turned into lessons
- skill_memory.json — knowledge state: concepts covered, dates, depth (v2)
- last_scored.json  — this run's ranking, so the dashboard rebuilds from state (v3)
- briefs/           — full lesson brief text, linked from lessons for Perplexity Q&A
"""
from storage.state import (
    filter_new,
    load_brief,
    load_last_scored,
    load_memory,
    load_seen,
    record_lesson,
    save_brief,
    save_last_scored,
    save_memory,
    save_seen,
)

__all__ = [
    "load_seen",
    "save_seen",
    "filter_new",
    "load_memory",
    "save_memory",
    "record_lesson",
    "load_last_scored",
    "save_last_scored",
    "save_brief",
    "load_brief",
]
