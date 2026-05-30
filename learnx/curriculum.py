"""LLM curriculum planner — ported/trimmed from LearnX-CLI (generation/curriculum.py).

Takes the markdown brief and plans a short sequence of teaching units sized to
the target duration. One LLM call; word budgets split across units by complexity.
"""
import logging

import config
from learnx.constants import (
    DEFAULT_DIFFICULTY,
    DIFFICULTY_CONTEXT,
    MAX_UNITS,
    MIN_UNIT_WORDS,
    MIN_UNITS,
    OVERHEAD_WORDS,
    WPM,
)
from learnx.llm import chat, parse_json_response
from learnx.models import TeachingUnit
from learnx.prompt_loader import load_prompt

log = logging.getLogger(__name__)


def plan(
    brief_md: str,
    title: str,
    duration_min: int = config.LESSON_DURATION_MIN,
    difficulty: str = DEFAULT_DIFFICULTY,
    chat_fn=chat,
) -> list[TeachingUnit]:
    """Return ordered teaching units for the brief, adapted to `difficulty`."""
    prompt = load_prompt("curriculum.txt").format(
        title=title,
        duration_min=duration_min,
        difficulty=difficulty,
        difficulty_context=DIFFICULTY_CONTEXT.get(difficulty, DIFFICULTY_CONTEXT[DEFAULT_DIFFICULTY]),
        min_units=MIN_UNITS,
        max_units=MAX_UNITS,
        brief=brief_md,
    )
    messages = [{"role": "user", "content": prompt}]
    log.info("Planning curriculum for '%s', %d min", title, duration_min)

    raw = chat_fn(messages, max_tokens=2000)
    try:
        data = parse_json_response(raw)
    except ValueError:
        retry = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": "Reply with the raw JSON array only."},
        ]
        data = parse_json_response(chat_fn(retry, max_tokens=2000))

    if not isinstance(data, list) or not data:
        raise ValueError("Curriculum planner returned no units")

    return _build_units(data, duration_min)


def _build_units(data: list, duration_min: int) -> list[TeachingUnit]:
    data = data[:MAX_UNITS]
    total_budget = duration_min * WPM - OVERHEAD_WORDS
    total_complexity = sum(_complexity(u) for u in data) or len(data)
    base = total_budget / total_complexity

    units: list[TeachingUnit] = []
    for i, u in enumerate(data):
        complexity = _complexity(u)
        word_budget = max(round(base * complexity), MIN_UNIT_WORDS)
        units.append(
            TeachingUnit(
                unit=i + 1,
                concept=str(u.get("concept", f"Unit {i + 1}")),
                word_budget=word_budget,
                complexity=complexity,
                key_facts=[str(f) for f in u.get("key_facts", [])],
                analogy=str(u.get("analogy", "")),
                misconception=str(u.get("misconception", "")),
                memory_hook=str(u.get("memory_hook", "")),
            )
        )
    log.info("Curriculum planned: %d units", len(units))
    return units


def _complexity(u: dict) -> int:
    try:
        return max(1, min(3, int(u.get("complexity", 2))))
    except (TypeError, ValueError):
        return 2
