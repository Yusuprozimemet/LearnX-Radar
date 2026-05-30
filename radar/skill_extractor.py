"""Extract skill/tool mentions across all source items via GLM-5.1.

Condenses every scraped item into one compact digest line, then makes a single
batched LLM call to pull out concrete, teachable skills — each tagged with the
distinct sources it appeared in. One call keeps us well inside the NVIDIA NIM
free-tier rate limit regardless of how many items were scraped.

A mention: {"skill": str, "sources": list[str], "evidence": str}
"""
import json
import logging
import re

import config
from learnx.llm import chat, parse_json_response
from radar.prompt_loader import load_prompt

log = logging.getLogger(__name__)

# Mention objects contain no nested objects (sources is a flat array), so each
# top-level {...} can be recovered individually if the array is truncated.
_OBJECT_RE = re.compile(r"\{[^{}]*\}")

_ITEM_TEXT_CAP = 200  # chars of item text per digest line — token hygiene


def _build_digest(items: list[dict]) -> str:
    lines = []
    for item in items:
        text = (item.get("text") or "").replace("\n", " ").strip()[:_ITEM_TEXT_CAP]
        lines.append(f"[{item['source']}] {item['title']} :: {text}")
    return "\n".join(lines)


def _clean(raw_mentions: object) -> list[dict]:
    """Validate/normalize the LLM's JSON into well-formed mentions."""
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
    return cleaned[: config.MAX_SKILL_MENTIONS]


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


def extract(items: list[dict], chat_fn=chat) -> list[dict]:
    """Return deduped skill mentions found across all items (one LLM call)."""
    if not items:
        return []

    prompt = load_prompt("extract.txt").format(digest=_build_digest(items))
    messages = [{"role": "user", "content": prompt}]
    log.info("Extracting skills from %d items", len(items))

    raw = chat_fn(messages, max_tokens=4000)
    try:
        data = parse_json_response(raw)
    except ValueError:
        data = _salvage(raw)

    mentions = _clean(data)
    log.info("Extracted %d skill mentions", len(mentions))
    return mentions
