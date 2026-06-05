"""Pulls the current Hacker News front page via the Algolia API.

Open-vocabulary discovery: the front page is what developers are reading right
now, written in their own words — a strong, query-free signal for emerging
skills/tools. Same no-auth Algolia API the hiring agent uses, different tag.

We deliberately do NOT fetch the linked article (latency/privacy) — the title
(plus any self-post text) is the discovery signal; grounding the eventual lesson
in article contents is the synthesis/enrichment job, not this layer's.
"""
import html
import re

import requests

import config

SEARCH_URL = "https://hn.algolia.com/api/v1/search"
ITEM_URL = "https://news.ycombinator.com/item?id={id}"

_TAG_RE = re.compile(r"<[^>]+>")


def fetch() -> list[dict]:
    try:
        resp = requests.get(
            SEARCH_URL,
            params={"tags": "front_page"},
            headers={"User-Agent": config.USER_AGENT},
            timeout=20,
        )
        resp.raise_for_status()
        hits = resp.json().get("hits", [])
    except (requests.RequestException, ValueError) as exc:
        print(f"[hn_front] fetch failed: {exc}")
        return []
    return _items_from_hits(hits)


def _items_from_hits(hits: list[dict]) -> list[dict]:
    """Pure parse: Algolia front_page hits -> normalized items. Offline-testable."""
    items: list[dict] = []
    for hit in hits:
        title = (hit.get("title") or "").strip()
        object_id = hit.get("objectID")
        if not title or not object_id:
            continue  # job/poll rows without a title, or malformed hits
        # External link when present; Ask/Show HN have no `url` -> link to the
        # HN discussion itself so the item still resolves.
        url = (hit.get("url") or "").strip() or ITEM_URL.format(id=object_id)
        story_text = hit.get("story_text") or ""
        if story_text:
            story_text = html.unescape(_TAG_RE.sub(" ", story_text)).strip()
        text = (title + " " + story_text).strip()
        points = hit.get("points")
        items.append(
            {
                "id": f"hnfp:{object_id}",
                "source": "HN Front Page",
                "title": title,
                "url": url,
                "text": text,
                "meta": f"hn · {points} pts" if points is not None else "hn",
            }
        )
    return items


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fetched = fetch()
    print(f"{len(fetched)} front-page stories")
    for item in fetched[:5]:
        print("-", item["meta"], "|", item["title"])
