"""Extracts employer skill demand from the HN "Who is Hiring?" thread.

Uses the Algolia HN API (no auth). The monthly thread is posted by the
`whoishiring` account, so we filter by `author_whoishiring` to find the current
thread (a plain "who is hiring" query returns the wrong story). Each top-level
comment is one job post written in real employer language — the best free
signal for in-demand skills.
"""
import html
import re

import requests

import config

SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
ITEM_URL = "https://hn.algolia.com/api/v1/items/{id}"
COMMENT_URL = "https://news.ycombinator.com/item?id={id}"

_TAG_RE = re.compile(r"<[^>]+>")


def fetch() -> list[dict]:
    story = _latest_hiring_story()
    if story is None:
        return []
    story_id, label = story
    return _fetch_comments(story_id, label)


def _latest_hiring_story() -> tuple[int, str] | None:
    """Return (objectID, thread_title) of the newest whoishiring thread."""
    try:
        resp = requests.get(
            SEARCH_URL,
            params={
                "tags": "story,author_whoishiring",
                "query": "hiring",
                "hitsPerPage": 1,
            },
            headers={"User-Agent": config.USER_AGENT},
            timeout=20,
        )
        resp.raise_for_status()
        hits = resp.json()["hits"]
    except (requests.RequestException, KeyError, ValueError) as exc:
        print(f"[hn_hiring] thread lookup failed: {exc}")
        return None
    if not hits:
        return None
    return int(hits[0]["objectID"]), hits[0].get("title", "Who is hiring?")


def _fetch_comments(story_id: int, label: str) -> list[dict]:
    try:
        resp = requests.get(
            ITEM_URL.format(id=story_id),
            headers={"User-Agent": config.USER_AGENT},
            timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"[hn_hiring] comment fetch failed: {exc}")
        return []
    return _items_from_item(data, label)


def _items_from_item(data: dict, label: str) -> list[dict]:
    """Pure parse: Algolia item JSON -> one item per comment. Offline-testable."""
    children = data.get("children") or []
    items: list[dict] = []
    for child in children[: config.HN_HIRING_LIMIT]:
        raw = child.get("text")
        if not raw:
            continue  # deleted/empty comment
        text = html.unescape(_TAG_RE.sub(" ", raw)).strip()
        if not text:
            continue
        cid = child["id"]
        items.append(
            {
                "id": f"hn:{cid}",
                "source": "HN Hiring",
                "title": text.split("\n")[0][:80],
                "url": COMMENT_URL.format(id=cid),
                "text": text,
                "meta": f"hiring · {label}",
            }
        )
    return items


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    fetched = fetch()
    print(f"{len(fetched)} job posts")
    for item in fetched[:3]:
        print("-", item["title"])
