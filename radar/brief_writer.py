"""Synthesize a teaching markdown brief for the top-ranked skill (one LLM call).

The brief is what a human author would hand to the learnx curriculum stage: a
structured .md explaining the skill, why it's trending now, and what to cover.
It becomes the input document for the audio pipeline (Day 3).

v2 hook: when skill_memory holds prior lessons, the prompt gains a
"connects to what you learned" line. For v1 (empty memory) that stays blank.
"""
import logging

import config
from learnx.llm import chat
from radar.prompt_loader import load_prompt

log = logging.getLogger(__name__)


def _prior_context(memory: dict) -> str:
    """A one-line continuity hint if anything has been taught before, else ''."""
    taught = list(memory.get("skills", {}).keys())
    if not taught:
        return ""
    recent = ", ".join(taught[-3:])
    return (
        f"PREVIOUSLY TAUGHT: {recent}\n"
        "If relevant, open by briefly connecting this skill to one of those.\n"
    )


def write(skill: dict, memory: dict, chat_fn=chat) -> str:
    """Return a markdown teaching brief for the given scored skill."""
    prompt = load_prompt("brief.txt").format(
        skill=skill["skill"],
        evidence=skill.get("evidence", ""),
        sources=", ".join(skill.get("sources", [])) or "multiple sources",
        prior_context=_prior_context(memory),
    )
    log.info("Writing brief for skill: %s", skill["skill"])
    brief = chat_fn([{"role": "user", "content": prompt}], max_tokens=1500).strip()
    return brief
