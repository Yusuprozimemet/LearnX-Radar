"""Scrapes GitHub Trending — rising repos are a proxy for emerging tools.

No auth required: the trending pages are public HTML. We scrape one page per
configured language and normalize each repo to the shared item shape.

Dedup keys on repo identity (gh:{owner/repo}), not the date — a repo trending
two days running is the same learnable thing, so the repeat is suppressed.
"""
import requests
from bs4 import BeautifulSoup

import config

TRENDING_URL = "https://github.com/trending/{language}?since={since}"


def _headers() -> dict:
    return {"User-Agent": config.USER_AGENT, "Accept": "text/html"}


def fetch() -> list[dict]:
    items: list[dict] = []
    for language in config.TRENDING_LANGUAGES:
        url = TRENDING_URL.format(language=language, since=config.TRENDING_SINCE)
        try:
            resp = requests.get(url, headers=_headers(), timeout=20)
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"[github_trending] {language} failed: {exc}")
            continue
        items.extend(_parse(resp.text, language))
    return items


def _parse(page_html: str, language: str) -> list[dict]:
    soup = BeautifulSoup(page_html, "html.parser")
    items: list[dict] = []
    for row in soup.select("article.Box-row"):
        anchor = row.select_one("h2 a")
        if anchor is None:
            continue
        repo = anchor.get("href", "").strip("/")
        if not repo or "/" not in repo:
            continue

        desc_el = row.select_one("p")
        desc = desc_el.get_text(strip=True) if desc_el else ""

        stars_today = ""
        for span in row.select("span.d-inline-block.float-sm-right"):
            stars_today = span.get_text(strip=True)
            break

        items.append(
            {
                "id": f"gh:{repo}",
                "source": "GitHub Trending",
                "title": repo,
                "url": f"https://github.com/{repo}",
                "text": desc,
                "meta": f"{language} · {stars_today}".strip(" ·"),
            }
        )
    return items


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for item in fetch():
        print(item["meta"], "|", item["title"])
