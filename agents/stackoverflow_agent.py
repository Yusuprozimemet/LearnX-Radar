"""Tracks Stack Overflow tag frequency — week-over-week delta signals growth.

Uses the public Stack Exchange API (no auth). For each tracked tag we read the
total recent question count and compare against the prior reading stored in
skill_memory["so_counts"]; a rising delta is a strong "skill heating up" signal.

This agent only READS prior counts (passed in via `prior_counts`); persisting
the new counts stays in main.py/storage so the agent stays pure.
"""
from datetime import date

import requests

import config

API_URL = "https://api.stackexchange.com/2.3/questions"


def fetch(prior_counts: dict[str, int] | None = None) -> list[dict]:
    prior_counts = prior_counts or {}
    iso_week = "{0}-W{1:02d}".format(*date.today().isocalendar()[:2])
    items: list[dict] = []
    for tag in config.STACKOVERFLOW_TAGS:
        item = _fetch_tag(tag, prior_counts.get(tag), iso_week)
        if item is not None:
            items.append(item)
    return items


def _fetch_tag(tag: str, prior: int | None, iso_week: str) -> dict | None:
    try:
        resp = requests.get(
            API_URL,
            params={
                "site": "stackoverflow",
                "tagged": tag,
                "filter": "total",
                "pagesize": 1,
            },
            headers={"User-Agent": config.USER_AGENT},
            timeout=20,
        )
        resp.raise_for_status()
        total = int(resp.json()["total"])
    except (requests.RequestException, KeyError, ValueError, TypeError) as exc:
        print(f"[stackoverflow] {tag} failed: {exc}")
        return None

    delta = None if prior is None else total - prior
    return {
        "id": f"so:{tag}:{iso_week}",
        "source": "Stack Overflow",
        "title": f"{tag} questions rising",
        "url": f"https://stackoverflow.com/questions/tagged/{tag}",
        "text": f"Stack Overflow questions tagged {tag}: {total} (delta {delta})",
        "meta": f"stackoverflow · delta {delta}",
        # carried through so main.py can persist the new reading to memory
        "_so_count": {"tag": tag, "total": total},
    }


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for item in fetch():
        print(item["meta"], "|", item["title"])
