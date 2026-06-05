"""Web — read any URL as clean text via Jina Reader (r.jina.ai). Zero key.

Vendored from LearnX-Search/learnx_search/channels/web.py (v7 Day 24). This is
the spine of brief grounding: it full-reads the URLs the radar already collected
so the brief rests on real article text, not a 200-char snippet. Returns None on
blocked/errored/empty pages so we never cite a dead read.
"""
import re
import urllib.parse
import urllib.request

import config
from radar.research.base import Channel, Item

_JINA = "https://r.jina.ai/"

# Jina prefixes a metadata header ("Title: ...\nURL Source: ...\nMarkdown Content:\n")
# before the actual page. We pull Title from it, then keep only the body.
_BODY_MARKER = "Markdown Content:"
# GitHub profile pages embed a day-by-day contribution calendar — ~12k chars of
# "No contributions on June 1st." sentences that carry no signal but shove the
# useful tail past any read budget. Specific phrasing, safe to collapse anywhere.
_GH_CALENDAR = re.compile(
    r"(?:(?:No|\d[\d,]*)\s+contributions?\s+on\s+[A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th)\.\s*)+"
)
# Jina emits these diagnostics (not page content) when a target blocks/errors it —
# e.g. LinkedIn answers bots with HTTP 999. Drop them so an errored read that
# carries no real content collapses to empty (and is then dropped, not cited).
_JINA_WARNING = re.compile(r"^Warning: .*$", re.M)


def _clean(raw: str) -> tuple[str, str]:
    """Return (title, body) from a Jina document, stripped of header, diagnostics,
    and high-volume boilerplate. `body` is empty when the read produced no real
    content (blocked/errored page)."""
    title = ""
    for line in raw.splitlines():
        if line.startswith("Title:"):
            title = line[len("Title:"):].strip()
            break
    marker = raw.find(_BODY_MARKER)
    body = raw[marker + len(_BODY_MARKER):] if marker != -1 else raw
    body = _GH_CALENDAR.sub("", body)
    body = _JINA_WARNING.sub("", body)
    return title, body.strip()


class WebChannel(Channel):
    name = "web"
    description = "Read any web page / article as clean text (fallback reader)."
    language = "any"
    backends = ["Jina Reader"]
    tier = 0

    def can_handle(self, url: str) -> bool:
        return url.startswith("http://") or url.startswith("https://")

    def read(self, url: str) -> Item | None:
        req = urllib.request.Request(
            _JINA + url, headers={"User-Agent": config.USER_AGENT}
        )
        with urllib.request.urlopen(req, timeout=config.GROUNDING_HTTP_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        title, body = _clean(raw)
        if not body:  # blocked/errored/empty page — don't pass it off as a source
            return None
        return {
            "id": f"web:{url}",
            "source": "Web",
            "title": title or url,
            "url": url,
            "text": body,
            "meta": urllib.parse.urlparse(url).netloc,
        }

    def check(self):
        return "ok", "Jina Reader (r.jina.ai) — reads any URL, no key"


# Module-level singleton (channels are stateless) for ergonomic `web.read(url)`.
_CHANNEL = WebChannel()


def read(url: str) -> Item | None:
    return _CHANNEL.read(url)
