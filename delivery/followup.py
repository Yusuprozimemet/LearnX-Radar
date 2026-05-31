"""Build a Perplexity deep link seeded with the lesson brief *text*.

Replaces the old /recap Telegram bot: instead of a polling workflow, each
delivered lesson carries a one-tap link into a fresh Perplexity thread.

We embed the brief text directly in the query rather than linking to the raw
brief URL. Perplexity does not reliably fetch an external link, so the old
"read this URL" prompt left it with no grounding — the whole point of the
button. Inlining the text gives Perplexity the lesson content up front. The
brief is condensed and trimmed to `config.FOLLOWUP_BRIEF_CHARS` so the encoded
query keeps the deep-link URL within what a Telegram inline button accepts.
"""
import re
from urllib.parse import quote

import config

_SEARCH = "https://www.perplexity.ai/search/new?q={q}"


def _condense(brief_md: str, limit: int) -> str:
    """Flatten brief markdown to compact prose and trim to `limit` chars.

    Strips heading/bullet markers and collapses whitespace so the embedded text
    is dense (every char costs ~1.3-3x once URL-encoded). When over budget, cuts
    at the last sentence boundary if one falls late enough, else hard-trims and
    appends an ellipsis — so the seeded context never ends mid-word.
    """
    lines = []
    for raw in brief_md.splitlines():
        line = re.sub(r"^\s*#{1,6}\s*", "", raw)    # drop ATX heading markers
        line = re.sub(r"^\s*[*+-]\s+", "• ", line)  # bullets -> a compact glyph
        line = line.strip()
        if line:
            lines.append(line)
    text = re.sub(r"\s+", " ", " ".join(lines)).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    if end >= limit * 0.6:  # honor a sentence break only if it isn't too early
        return cut[: end + 1]
    return cut.rstrip() + "…"


def perplexity_url(skill: str, brief_md: str) -> str:
    """Deep link to a Perplexity thread seeded with the brief text for `skill`."""
    brief = _condense(brief_md, config.FOLLOWUP_BRIEF_CHARS)
    query = (
        f"I just studied a short audio lesson on {skill}. Here is the lesson "
        f"brief — use it as the grounding context and answer my follow-up "
        f"questions from it:\n\n{brief}\n\n"
        f"To start: what should I learn next about {skill}?"
    )
    return _SEARCH.format(q=quote(query))


def quiz_url(skill: str, brief_md: str) -> str:
    """Deep link to a Perplexity thread that quizzes the user on `skill`.

    Active-recall self-test grounded in the brief text (embedded, not linked).
    The query below is the single tunable line that sets the quiz format — swap
    it for a multiple-choice prompt if ever wanted; the default is open recall.
    """
    brief = _condense(brief_md, config.FOLLOWUP_BRIEF_CHARS)
    query = (
        f"Quiz me on a past lesson about {skill} to check what I retained. Here "
        f"is the lesson brief to base the quiz on:\n\n{brief}\n\n"
        f"Now ask me 2-3 questions ONE AT A TIME: mix a recall question ('in "
        f"your own words...') and an applied/scenario question. Wait for my "
        f"answer before the next. After each answer, grade it and correct me "
        f"using the brief. Start now with question one."
    )
    return _SEARCH.format(q=quote(query))
