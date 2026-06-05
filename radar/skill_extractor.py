"""Extract skill/tool mentions across all collected items.

v7 Day 25 — map-reduce + deterministic attribution (specs/v7/day25):

    MAP        chunk the corpus -> extract candidate skills per chunk (LLM, recall)
    REDUCE     merge variant names (lexical normalize + config.SKILL_ALIASES)
    ATTRIBUTE  for each candidate, scan ALL items -> the REAL set of sources that
               mention it + an evidence snippet (deterministic, no LLM tallying)

This fixes the single-pass extractor's two accuracy holes: recall (one capped
pass dropped the long tail) and attribution (the demand weight rested on the LLM
correctly counting sources across ~24k tokens). The LLM now only *discovers*;
source attribution — what the demand weight sums — is an exact corpus scan.

`config.EXTRACTION_MAPREDUCE = False` restores the legacy single-pass path.

A mention: {"skill": str, "sources": list[str], "evidence": str}
"""
import json
import logging
import re
from collections import Counter

import config
from learnx.llm import chat, parse_json_response
from radar.prompt_loader import load_prompt

log = logging.getLogger(__name__)

# Mention objects contain no nested objects (sources is a flat array), so each
# top-level {...} can be recovered individually if the array is truncated.
_OBJECT_RE = re.compile(r"\{[^{}]*\}")

_ITEM_TEXT_CAP = 200  # chars of item text per digest line — token hygiene
_EVIDENCE_CAP = 140   # chars of evidence snippet when derived from a corpus item


# --- digest / chunking -------------------------------------------------------

def _digest_line(item: dict) -> str:
    text = (item.get("text") or "").replace("\n", " ").strip()[:_ITEM_TEXT_CAP]
    return f"[{item['source']}] {item['title']} :: {text}"


def _build_digest(items: list[dict]) -> str:
    return "\n".join(_digest_line(item) for item in items)


def _est_tokens(s: str) -> int:
    """Cheap token estimate (~chars/4) — avoids a tiktoken dep in the hot path."""
    return len(s) // 4


def _chunk_by_tokens(items: list[dict], budget: int) -> list[list[dict]]:
    """Split items into chunks whose digest stays within `budget` tokens.

    Sized by tokens, not item count: HN Hiring items are long, SO items tiny.
    """
    chunks: list[list[dict]] = []
    cur: list[dict] = []
    cur_tok = 0
    for item in items:
        t = _est_tokens(_digest_line(item))
        if cur and cur_tok + t > budget:
            chunks.append(cur)
            cur, cur_tok = [], 0
        cur.append(item)
        cur_tok += t
    if cur:
        chunks.append(cur)
    return chunks


# --- LLM response handling (shared by map + legacy) --------------------------

def _clean(raw_mentions: object, cap: bool = True) -> list[dict]:
    """Validate/normalize the LLM's JSON into well-formed mentions.

    `cap=True` trims to config.MAX_SKILL_MENTIONS (legacy single-pass); the map
    step passes cap=False so per-chunk recall isn't throttled.
    """
    if not isinstance(raw_mentions, list):
        return []
    cleaned: list[dict] = []
    for m in raw_mentions:
        if not isinstance(m, dict):
            continue
        skill = str(m.get("skill", "")).strip()
        if not skill:
            continue
        sources = [str(s).strip() for s in m.get("sources", []) if str(s).strip()]
        cleaned.append(
            {
                "skill": skill,
                "sources": sources,
                "evidence": str(m.get("evidence", "")).strip(),
            }
        )
    return cleaned[: config.MAX_SKILL_MENTIONS] if cap else cleaned


def _salvage(raw: str) -> list[dict]:
    """Recover whatever complete mention objects exist in a truncated reply.

    A daily cron shouldn't die because the model ran long and the JSON array got
    cut mid-element; we keep every object that parses and drop the partial tail.
    """
    recovered = []
    for match in _OBJECT_RE.findall(raw):
        try:
            recovered.append(json.loads(match))
        except json.JSONDecodeError:
            continue
    if recovered:
        log.warning("Salvaged %d mentions from unparseable response", len(recovered))
    return recovered


def _extract_chunk(items: list[dict], chat_fn, cap: bool) -> list[dict]:
    """One LLM extraction call over `items` -> cleaned candidate mentions."""
    prompt = load_prompt("extract.txt").format(digest=_build_digest(items))
    raw = chat_fn([{"role": "user", "content": prompt}], max_tokens=4000)
    try:
        data = parse_json_response(raw)
    except ValueError:
        data = _salvage(raw)
    return _clean(data, cap=cap)


# --- REDUCE: canonicalize + merge variants -----------------------------------

def _canonical(name: str) -> str:
    """Lowercase, strip, collapse whitespace, then apply the alias map."""
    n = re.sub(r"\s+", " ", name.strip().lower())
    return config.SKILL_ALIASES.get(n, n)


def _reduce(candidates: list[dict]) -> dict[str, dict]:
    """Group candidates by canonical name, unioning surfaces/sources/evidence."""
    groups: dict[str, dict] = {}
    for c in candidates:
        key = _canonical(c["skill"])
        if not key:
            continue
        g = groups.setdefault(
            key,
            {"surfaces": set(), "llm_sources": set(), "evidence": "", "display": Counter()},
        )
        surface = c["skill"].strip()
        g["surfaces"].add(surface)
        g["display"][surface] += 1
        g["llm_sources"].update(c["sources"])
        if not g["evidence"] and c["evidence"]:
            g["evidence"] = c["evidence"]
    return groups


# --- ATTRIBUTE: deterministic source sets ------------------------------------

def _is_ambiguous(key: str) -> bool:
    return key in config.AMBIGUOUS_SHORT_SKILLS or len(key) <= 2


def _term_pattern(term: str) -> re.Pattern:
    """Match `term` as a whole token/phrase, not a substring.

    Flanked by non-alphanumerics (so "go" won't match "going", and punctuation
    skills like "c++"/"node.js" still match); multi-word terms match as a phrase
    with flexible whitespace; case-insensitive.
    """
    parts = [re.escape(w) for w in term.split() if w]
    body = r"\s+".join(parts)
    return re.compile(rf"(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])", re.IGNORECASE)


def _surfaces_for(key: str, surfaces: set[str]) -> set[str]:
    """All surface forms to scan for: observed names + canonical + alias keys."""
    out = {s for s in surfaces if s}
    out.add(key)
    out.update(a for a, v in config.SKILL_ALIASES.items() if v == key)
    return out


def _haystack(item: dict) -> str:
    return f"{item.get('title', '')} {item.get('text', '')}"


def _attribute(groups: dict[str, dict], items: list[dict]) -> list[dict]:
    """Turn merged groups into mentions with REAL source sets from a corpus scan.

    Ambiguous short names (and any whose phrasing isn't found in the corpus) fall
    back to the map step's LLM-reported sources — the safety valve for the cases
    where exact matching is unreliable.
    """
    mentions: list[dict] = []
    for key, g in groups.items():
        display = g["display"].most_common(1)[0][0]
        llm_sources = sorted(g["llm_sources"])

        if _is_ambiguous(key):
            sources, evidence = llm_sources, g["evidence"]
        else:
            patterns = [_term_pattern(s) for s in _surfaces_for(key, g["surfaces"]) if s.strip()]
            matched = [it for it in items if any(p.search(_haystack(it)) for p in patterns)]
            if matched:
                sources = sorted({it["source"] for it in matched})
                evidence = g["evidence"] or matched[0].get("title", "")[:_EVIDENCE_CAP]
            else:  # corpus phrasing differs from the LLM's term — trust the LLM
                sources, evidence = llm_sources, g["evidence"]

        mentions.append({"skill": display, "sources": sources, "evidence": evidence})

    # Recall is the goal, but cap before scoring as a safety valve; keep the
    # best-attributed first so the cap drops the weakest candidates.
    mentions.sort(key=lambda m: -len(m["sources"]))
    return mentions[: config.EXTRACTION_MAX_CANDIDATES]


# --- public API --------------------------------------------------------------

def _extract_single_pass(items: list[dict], chat_fn) -> list[dict]:
    """Legacy: one LLM call over the whole corpus (rollback path)."""
    log.info("Extracting skills from %d items (single pass)", len(items))
    return _extract_chunk(items, chat_fn, cap=True)


def extract(items: list[dict], chat_fn=chat) -> list[dict]:
    """Return skill mentions found across all items.

    Map-reduce by default (recall + deterministic attribution); legacy single
    pass when config.EXTRACTION_MAPREDUCE is False.
    """
    if not items:
        return []
    if not config.EXTRACTION_MAPREDUCE:
        return _extract_single_pass(items, chat_fn)

    chunks = _chunk_by_tokens(items, config.EXTRACTION_CHUNK_TOKENS)
    candidates: list[dict] = []
    failed = 0
    for i, chunk in enumerate(chunks):
        try:
            candidates.extend(_extract_chunk(chunk, chat_fn, cap=False))
        except Exception as exc:  # one bad chunk must not kill the run
            failed += 1
            log.warning("map chunk %d/%d failed: %s", i + 1, len(chunks), exc)

    groups = _reduce(candidates)
    mentions = _attribute(groups, items)
    # Surface recall in the cron log (failed chunks explain a low candidate count).
    fail_note = f" ({failed} FAILED)" if failed else ""
    print(
        f"[extract] map-reduce: {len(items)} items -> {len(chunks)} chunks{fail_note} "
        f"-> {len(candidates)} raw -> {len(mentions)} candidates"
    )
    return mentions
