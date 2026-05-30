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


_RECENT_LESSONS = 5  # how many prior lessons to offer as bridge candidates


def _prior_context(memory: dict, current_skill: str) -> str:
    """Offer recent prior lessons so the brief can bridge to a related one.

    Lists each as `skill — summary` and instructs a genuine connection only when
    one is actually related — no forced "as we discussed last time" filler.
    """
    skills = memory.get("skills", {})
    prior = [(name, data.get("summary", "")) for name, data in skills.items() if name != current_skill]
    if not prior:
        return ""
    lines = "\n".join(f"- {name}: {summary}" for name, summary in prior[-_RECENT_LESSONS:])
    return (
        "PREVIOUSLY TAUGHT LESSONS:\n"
        f"{lines}\n"
        f"If one of these is genuinely related to {current_skill}, open the brief "
        "with a single sentence bridging from it to today's topic. If none is truly "
        "related, do not force a connection.\n"
    )


def write(skill: dict, memory: dict, chat_fn=chat) -> str:
    """Return a markdown teaching brief for the given scored skill."""
    prompt = load_prompt("brief.txt").format(
        skill=skill["skill"],
        evidence=skill.get("evidence", ""),
        sources=", ".join(skill.get("sources", [])) or "multiple sources",
        prior_context=_prior_context(memory, skill["skill"]),
    )
    log.info("Writing brief for skill: %s", skill["skill"])
    brief = chat_fn([{"role": "user", "content": prompt}], max_tokens=1500).strip()
    return brief
