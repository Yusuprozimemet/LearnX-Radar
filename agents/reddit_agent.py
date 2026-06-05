"""Pulls top weekly posts from configured subreddits via Reddit's public RSS.

Open-vocabulary discovery: unlike the tag/language-locked sources (Stack
Overflow, GitHub, dev.to), subreddit front pages surface skill/tool names we
never pre-listed. Reddit discontinued self-service OAuth for new apps and 403s
the `.json` API from datacenter IPs, but the per-subreddit Atom feed
(`/r/{sub}/top.rss`) stays open, needs no auth, and returns 200 from CI — proven
in the sibling Daily-CronJob's Actions cron. A descriptive User-Agent is required
(Reddit 429s the default urllib/requests one). Weekly window (`t=week`) is used
because a daily one is too volatile to be a skill trend.
"""
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

import config

FEED_URL = "https://www.reddit.com/r/{sub}/top.rss?t=week&limit={limit}"
_ATOM = "{http://www.w3.org/2005/Atom}"


def _text(entry: ET.Element, tag: str) -> str:
    el = entry.find(f"{_ATOM}{tag}")
    return (el.text or "").strip() if el is not None and el.text else ""


def fetch() -> list[dict]:
    items: list[dict] = []
    headers = {"User-Agent": config.USER_AGENT}
    for sub in config.REDDIT_SUBREDDITS:
        url = FEED_URL.format(sub=sub, limit=config.REDDIT_LIMIT)
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[reddit] r/{sub} failed: {exc}")
            continue
        items.extend(_parse(resp.content, sub))
    return items


def _parse(content: bytes, sub: str) -> list[dict]:
    """Pure parse: Atom feed bytes -> normalized items. Offline-testable."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        print(f"[reddit] r/{sub} parse failed: {exc}")
        return []

    items: list[dict] = []
    for entry in root.findall(f"{_ATOM}entry"):
        # Atom <id> is "t3_<postid>"; keep just the post id so a post that stays
        # hot all week dedups to one stable item (like gh:{owner/repo}).
        raw_id = _text(entry, "id").rsplit("_", 1)[-1]
        title = _text(entry, "title")
        link_el = entry.find(f"{_ATOM}link")
        url = link_el.get("href", "") if link_el is not None else ""
        if not raw_id or not title or not url:
            continue
        desc = BeautifulSoup(_text(entry, "content"), "html.parser").get_text(
            " ", strip=True
        )
        items.append(
            {
                "id": f"rd:{raw_id}",
                "source": "Reddit",
                "title": title,
                "url": url,
                "text": desc[:300],
                "meta": f"reddit · r/{sub}",
            }
        )
    return items


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for item in fetch():
        print(item["meta"], "|", item["title"])
