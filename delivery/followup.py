"""Build a Perplexity deep link that pre-loads today's lesson brief.

Replaces the old /recap Telegram bot: instead of answering follow-up questions
in Telegram (which needed a polling workflow), each delivered lesson carries a
one-tap link into a fresh Perplexity thread that already has the full brief as
context, so the user can keep asking there.

The brief is committed to the repo by the radar workflow, so its raw URL is
deterministic. Note: the link resolves once that commit is pushed (seconds after
the run), so it 404s only in the brief window before the push completes.
"""
from urllib.parse import quote

import config

_SEARCH = "https://www.perplexity.ai/search/new?q={q}"


def perplexity_url(skill: str, brief_file: str) -> str:
    """Deep link to a Perplexity thread seeded with the brief for `skill`."""
    brief_url = f"{config.BRIEFS_RAW_BASE}/{brief_file}"
    query = (
        f"I just studied a short audio lesson on {skill}. Read this lesson brief "
        f"and answer my follow-up questions, grounded in it: {brief_url} "
        f"To start: what should I learn next about {skill}?"
    )
    return _SEARCH.format(q=quote(query))


def quiz_url(skill: str, brief_file: str) -> str:
    """Deep link to a Perplexity thread that quizzes the user on `skill`.

    Active-recall self-test grounded in the committed brief. The query below is
    the single tunable line that sets the quiz format — swap it for a
    multiple-choice prompt if ever wanted; the default is open-ended recall.
    """
    brief_url = f"{config.BRIEFS_RAW_BASE}/{brief_file}"
    query = (
        f"Quiz me on a past lesson about {skill} to check what I retained. Read "
        f"this brief: {brief_url}. Ask me 2-3 questions ONE AT A TIME — mix a "
        f"recall question ('in your own words...') and an applied/scenario "
        f"question. Wait for my answer before the next. After each answer, grade "
        f"it and correct me using the brief. Start now with question one."
    )
    return _SEARCH.format(q=quote(query))
