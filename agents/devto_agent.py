"""Pulls top dev.to posts per tag via public RSS — community buzz by topic.

dev.to exposes a per-tag RSS feed at https://dev.to/feed/tag/<tag> (no auth).
We read the configured tags and normalize each entry to the shared item shape.
"""
import re

import feedparser

import config

FEED_URL = "https://dev.to/feed/tag/{tag}"

# dev.to tag feeds carry SEO spam, mostly "buy/verified <service> accounts"
# (the service word, e.g. Binance, sits between "verified" and "accounts", so a
# naive adjacent match misses it). Drop titles matching an obvious-spam pattern.
_SPAM_RE = re.compile(
    r"\b(cheap|smm|backlinks?|followers?)\b"
    r"|\b(buy|verified|trusted)\b.*\baccounts?\b"
    r"|\b(binance|paypal|wise|coinbase|cash ?app|venmo|revolut)\b.*\baccounts?\b",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")  # strip HTML from summaries


def fetch() -> list[dict]:
    items: list[dict] = []
    for tag in config.DEVTO_TAGS:
        items.extend(_fetch_tag(tag))
    return items


def _fetch_tag(tag: str) -> list[dict]:
    feed = feedparser.parse(FEED_URL.format(tag=tag))
    return _items_from_feed(feed, tag)


def _items_from_feed(feed, tag: str) -> list[dict]:
    """Pure parse: feedparser result -> normalized items. Offline-testable."""
    items: list[dict] = []
    for entry in feed.entries[: config.DEVTO_LIMIT]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link or _SPAM_RE.search(title):
            continue
        tags = [t.get("term", "") for t in entry.get("tags", []) if t.get("term")]
        summary = _TAG_RE.sub(" ", entry.get("summary", "")).strip()
        text = (summary + " " + " ".join(tags)).strip()
        items.append(
            {
                "id": f"devto:{link}",
                "source": "dev.to",
                "title": title,
                "url": link,
                "text": text,
                "meta": f"dev.to · {tag}",
            }
        )
    return items


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for item in fetch():
        print(item["meta"], "|", item["title"])
