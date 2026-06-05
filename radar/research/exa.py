"""Exa — neural web search via the Exa REST API (https://exa.ai).

Vendored from LearnX-Search/learnx_search/channels/exa.py (v7 Day 24). Adds
fresh, beyond-corpus web results to brief grounding. Needs a free EXA_API_KEY;
without it `search` returns [] so grounding falls back to the day's own URLs and
the run never fails.
"""
import json
import urllib.request

import config
from radar.research.base import Channel, Item

_ENDPOINT = "https://api.exa.ai/search"


class ExaChannel(Channel):
    name = "exa"
    description = "Neural web search across the open internet — fresh, general queries."
    language = "any"
    backends = ["Exa API"]
    tier = 1

    def can_handle(self, url: str) -> bool:
        return False  # search-only

    def search(self, query: str, limit: int = 5) -> list[Item]:
        if not config.EXA_API_KEY or limit < 1:
            return []  # Exa rejects numResults<1 with HTTP 400
        # type="auto" + highlights per the canonical Exa guide: query-relevant
        # excerpts, token-efficient, ideal for downstream synthesis.
        body = json.dumps(
            {"query": query, "type": "auto", "numResults": limit,
             "contents": {"highlights": True}}
        ).encode("utf-8")
        req = urllib.request.Request(
            _ENDPOINT,
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-api-key": config.EXA_API_KEY,
                "User-Agent": config.USER_AGENT,
            },
        )
        with urllib.request.urlopen(req, timeout=config.GROUNDING_HTTP_TIMEOUT_S) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items: list[Item] = []
        for r in data.get("results", [])[:limit]:
            url = r.get("url", "")
            highlights = r.get("highlights") or []
            text = "\n".join(highlights) if highlights else (r.get("text", "") or "")
            items.append(
                {
                    "id": f"exa:{url}",
                    "source": "Exa Web",
                    "title": r.get("title", "") or url,
                    "url": url,
                    "text": text,
                    "meta": r.get("author", "") or r.get("publishedDate", "") or "",
                }
            )
        return items

    def check(self):
        if not config.EXA_API_KEY:
            return "warn", "Set EXA_API_KEY (free at exa.ai) to enable web search"
        return "ok", "Exa API key configured — web search ready"


_CHANNEL = ExaChannel()


def search(query: str, limit: int = 5) -> list[Item]:
    return _CHANNEL.search(query, limit)
