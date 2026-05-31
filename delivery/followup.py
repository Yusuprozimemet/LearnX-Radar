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
