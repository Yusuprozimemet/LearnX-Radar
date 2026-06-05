"""Pulls the hottest Lobste.rs stories via its public RSS feed.

Open-vocabulary discovery with a higher signal/noise ratio than dev.to: Lobsters
is a small, curated, invite-only community, so its front page skews toward
substantive engineering discussion. No auth; the feed exposes per-story tags
(e.g. rust, ai, databases) that carry the topic signal.
"""
import re

import feedparser

import config

FEED_URL = "https://lobste.rs/rss"

_TAG_RE = re.compile(r"<[^>]+>")  # strip HTML from summaries


def fetch() -> list[dict]:
    feed = feedparser.parse(FEED_URL)
    return _items_from_feed(feed)


def _items_from_feed(feed) -> list[dict]:
    """Pure parse: feedparser result -> normalized items. Offline-testable."""
    items: list[dict] = []
    for entry in feed.entries[: config.LOBSTERS_LIMIT]:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue
        tags = [t.get("term", "") for t in entry.get("tags", []) if t.get("term")]
        summary = _TAG_RE.sub(" ", entry.get("summary", "")).strip()
        text = (summary + " " + " ".join(tags)).strip()
        items.append(
            {
                "id": f"lob:{link}",
                "source": "Lobste.rs",
                "title": title,
                "url": link,
                "text": text,
                "meta": "lobste.rs",
            }
        )
    return items


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for item in fetch():
        print(item["meta"], "|", item["title"])
