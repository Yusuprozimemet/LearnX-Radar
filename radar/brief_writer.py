"""Synthesize a teaching markdown brief for the top-ranked skill (one LLM call).

The brief is what a human author would hand to the learnx curriculum stage: a
structured .md explaining the skill, why it's trending now, and what to cover.
It becomes the input document for the audio pipeline (Day 3).

v2 hook: when skill_memory holds prior lessons, the prompt gains a
"connects to what you learned" line. For v1 (empty memory) that stays blank.
"""
import logging
import re
from datetime import date, timedelta

import config
from learnx.llm import chat
from radar import privacy, research
from radar.prompt_loader import load_prompt

log = logging.getLogger(__name__)

# Evergreen "what is X" explainer URLs read like an encyclopedia, so a brief
# grounded on them comes out generic. Bias grounding toward dated discourse — the
# threads and posts that actually made the skill trend — so the lesson names real
# projects, techniques, and debates instead of textbook definitions.
_EVERGREEN_URL_RE = re.compile(
    r"/what-is|/discover/|/think/|/topics?/|/glossary|/wiki/|/learn/", re.IGNORECASE
)
_DISCOURSE_HOSTS = (
    "news.ycombinator.com", "reddit.com", "lobste.rs", "dev.to",
    "substack.com", "github.com", "lobsters",
)


def _discourse_bias(item: dict) -> int:
    """Rank nudge: sink evergreen explainers, float live discussion + day items.

    Applied as a *stable* re-sort over the lexically-ranked candidates, so it only
    breaks ties between similarly-relevant sources — it never promotes an
    off-topic source over an on-topic one.
    """
    url = (item.get("url") or "").lower()
    score = 0
    if _EVERGREEN_URL_RE.search(url):
        score -= 2
    if any(h in url for h in _DISCOURSE_HOSTS):
        score += 1
    # Day-scraped items carry a real channel label (HN/Reddit/...); Exa results
    # are tagged "Exa Web". The day's own items ARE the trend, so prefer them.
    if item.get("source") and item.get("source") != "Exa Web":
        score += 1
    return score

_NO_GROUNDING = (
    "(none retrieved — write from general knowledge; "
    "omit the Sources section and use no [n] markers)"
)


_RECENT_LESSONS = 5  # how many prior lessons to offer as bridge candidates

# Pull the "Do this in 5 minutes" section body so the audio outro can voice it.
_ACTION_RE = re.compile(
    r"^#+\s*Do this in 5 minutes\s*$(.*?)(?=^#+\s|\Z)",
    re.IGNORECASE | re.MULTILINE | re.DOTALL,
)


def action_step(brief_md: str) -> str:
    """Return the body text under the brief's 'Do this in 5 minutes' heading, or ''."""
    match = _ACTION_RE.search(brief_md or "")
    return match.group(1).strip() if match else ""


def _prior_context(memory: dict, current_skill: str) -> str:
    """Offer recent prior lessons so the brief can bridge to a related one.

    Lists each as `skill — summary` and instructs a genuine connection only when
    one is actually related — no forced "as we discussed last time" filler.
    """
    skills = memory.get("skills", {})
    prior = [
        (name, data.get("summary", ""))
        for name, data in skills.items()
        if name != current_skill
    ]
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


def _dedup_by_url(items: list[dict]) -> list[dict]:
    """Keep first occurrence of each url (id falls back to url)."""
    seen: set[str] = set()
    out: list[dict] = []
    for it in items:
        key = it.get("url") or it.get("id") or ""
        if key and key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


def _select_sources(skill: dict, items: list[dict], reader=None) -> list[dict]:
    """Pick + full-read the sources that ground the brief, in [n] order.

    Selects the day's items that mention the skill (+ fresh Exa results when a key
    is set), ranks them, full-reads the top GROUNDING_READ_TOP_N via the keyless
    Jina reader, and scrubs every fetched body. Failure-isolated and best-effort: a
    grounded brief is an upgrade, never a hard dependency, so any shortfall just
    yields fewer (or zero) sources. Returns the chosen items (enriched text), [].
    """
    if not config.GROUNDING_ENABLED:
        return []
    reader = reader or research.web.read
    name = skill["skill"]
    query = f"{name} {skill.get('evidence', '')}".strip()

    pool = list(items or [])
    try:
        # Discourse-flavored query + recency window: pull the current conversation
        # (new techniques, tooling, debates), not evergreen "what is X" pages.
        recent = None
        if config.GROUNDING_RECENCY_DAYS:
            recent = (date.today() - timedelta(days=config.GROUNDING_RECENCY_DAYS)).isoformat()
        pool += research.exa.search(
            f"{name}: latest tools, techniques, and debate among developers",
            limit=config.GROUNDING_READ_TOP_N,
            start_published_date=recent,
        )
    except Exception as exc:  # never let a search outage sink the brief
        log.warning("Exa search failed for %s: %s", name, exc)

    pool = _dedup_by_url(pool)
    ranked = research.filter_relevant(query, pool, keep=config.GROUNDING_CANDIDATES)
    # Stable re-rank: keep lexical relevance, but float discourse over explainers.
    ranked = sorted(ranked, key=_discourse_bias, reverse=True)
    to_read = ranked[: config.GROUNDING_READ_TOP_N]

    selected: list[dict] = []
    for it in to_read:
        full = None
        url = it.get("url", "")
        if url:
            try:
                full = reader(url)  # Jina full-page read; None on blocked/empty
            except Exception as exc:
                log.warning("Read failed for %s: %s", url, exc)
        chosen = full or it
        # Full reads + Exa highlights bypassed ingestion-time scrubbing; day items
        # were already scrubbed but re-scrubbing is idempotent. Scrub uniformly.
        chosen = {**chosen, "text": privacy.scrub(chosen.get("text", ""))}
        selected.append(chosen)
    return selected


def _sources_section(selected: list[dict]) -> str:
    """Build the ## Sources list from the REAL selected URLs, in [n] order.

    We append this deterministically instead of letting the LLM write URLs: models
    reliably fabricate plausible-but-fake source URLs (observed in the Day 24
    experiment), so the citation list is authored from data, never generated.
    """
    if not selected:
        return ""
    lines = [f"{i}. {it.get('url', '')}" for i, it in enumerate(selected, 1) if it.get("url")]
    return "\n\n## Sources\n" + "\n".join(lines) if lines else ""


def write(skill: dict, memory: dict, items: list[dict] | None = None, chat_fn=chat) -> str:
    """Return a markdown teaching brief for the given scored skill.

    When `items` (the day's scraped sources) are supplied and grounding is enabled,
    the brief is grounded in the real text of the sources that surfaced the skill
    (+ optional Exa results) with inline [n] citations; the ## Sources list mapping
    each [n] to its real URL is appended in code (never written by the LLM, which
    fabricates URLs). Without items / on any shortfall it falls back to the legacy
    ungrounded brief.
    """
    selected = _select_sources(skill, items or [])
    grounding = research.format_context(selected, config.GROUNDING_TEXT_CHARS) if selected else ""
    prompt = load_prompt("brief.txt").format(
        skill=skill["skill"],
        evidence=skill.get("evidence", ""),
        sources=", ".join(skill.get("sources", [])) or "multiple sources",
        prior_context=_prior_context(memory, skill["skill"]),
        grounding=grounding or _NO_GROUNDING,
    )
    log.info(
        "Writing brief for skill: %s (grounded=%s)", skill["skill"], bool(grounding)
    )
    brief = chat_fn([{"role": "user", "content": prompt}], max_tokens=1500).strip()
    return brief + _sources_section(selected)
