"""Relevance filter + context formatter, vendored from LearnX-Search synthesis.py.

Pure functions, no LLM, no network. `filter_relevant` ranks candidate items by
how many distinct query terms they cover (used to pick which sources ground a
brief); `format_context` renders the chosen items as numbered [n] blocks for the
brief prompt. Radar's brief_writer owns the actual synthesis call, so the
`synthesize` function from the source is intentionally NOT copied. (v7 Day 24)
"""
import re

_WORD = re.compile(r"[a-z0-9]+")
# Common question/filler words that carry no topical signal.
_STOP = {
    "the", "a", "an", "of", "to", "in", "for", "and", "or", "is", "are", "be",
    "how", "what", "why", "when", "which", "with", "do", "does", "did", "you",
    "your", "can", "should", "best", "practices", "practice", "guide", "using",
    "use", "about", "into", "from", "this", "that", "their", "them", "people",
}

Item = dict


def _query_terms(query: str) -> set[str]:
    return {t for t in _WORD.findall(query.lower()) if len(t) > 2 and t not in _STOP}


def filter_relevant(
    query: str,
    items: list[Item],
    keep: int = 10,
    min_terms: int = 1,
) -> list[Item]:
    """Rank items by distinct query-term coverage, drop noise, keep the top `keep`.

    Cheap (pure lexical). Items matching fewer than `min_terms` distinct query
    terms are dropped; the rest sort by coverage then title hits. If the query has
    no usable terms (or the filter would drop everything), input order is preserved
    so a run is never accidentally emptied.
    """
    terms = _query_terms(query)
    if not terms:
        return items[:keep]

    scored = []
    for it in items:
        title = (it.get("title") or "").lower()
        text = (it.get("text") or "").lower()
        distinct = sum(1 for t in terms if t in title or t in text)
        title_hits = sum(1 for t in terms if t in title)
        scored.append((distinct, title_hits, it))

    kept = [s for s in scored if s[0] >= min_terms]
    if not kept:  # never nuke the whole run — fall back to ranking everything
        kept = scored
    kept.sort(key=lambda s: (s[0], s[1]), reverse=True)
    return [it for _, _, it in kept[:keep]]


def format_context(items: list[Item], text_chars: int) -> str:
    """Render items as numbered, source-tagged [n] blocks for a synthesis prompt."""
    blocks = []
    for i, it in enumerate(items, 1):
        text = (it.get("text") or "")[:text_chars]
        blocks.append(
            f"[{i}] {it['source']} — {it['title']}\nURL: {it['url']}\n{text}".strip()
        )
    return "\n\n".join(blocks)
