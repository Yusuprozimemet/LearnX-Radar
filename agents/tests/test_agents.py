"""Offline parse tests for the data-collection agents.

Each test runs the pure parse path over a saved fixture (no live network), and
asserts the shared item contract plus the key source-specific fields.
"""
import json
from pathlib import Path

import feedparser

from agents import devto_agent, github_trending_agent, hn_hiring_agent, stackoverflow_agent

FIXTURES = Path(__file__).parent / "fixtures"

REQUIRED_KEYS = {"id", "source", "title", "url", "text", "meta"}


def _assert_contract(items):
    assert items, "expected at least one item"
    for item in items:
        assert REQUIRED_KEYS <= set(item), f"missing keys: {REQUIRED_KEYS - set(item)}"
        for key in ("id", "source", "title", "url"):
            assert item[key], f"empty {key} in {item}"


def test_github_trending_parse():
    html = (FIXTURES / "trending_python.html").read_text(encoding="utf-8")
    items = github_trending_agent._parse(html, "python")
    _assert_contract(items)
    for item in items:
        assert item["id"].startswith("gh:")
        assert item["url"].startswith("https://github.com/")
        assert "/" in item["title"]  # owner/repo


def test_devto_parse_and_spam_filter():
    feed = feedparser.parse(str(FIXTURES / "devto_rust.xml"))
    items = devto_agent._items_from_feed(feed, "rust")
    _assert_contract(items)
    for item in items:
        assert item["id"].startswith("devto:")
        assert not devto_agent._SPAM_RE.search(item["title"])


def test_devto_spam_patterns():
    """Known SEO-spam titles (seen live) must be flagged; real posts must not."""
    spam = [
        "Trusted Platform for Verified Binance Accounts",
        "Best Site to Buy Verified Wise Accounts Online",
        "Buy Verified PayPal Accounts",
        "Cheap SMM panel followers",
    ]
    legit = [
        "Building a Rust CLI with clap",
        "Why I switched my AI pipeline to DuckDB",
        "Managing accounts payable automation in Python",  # 'accounts' alone is fine
    ]
    for title in spam:
        assert devto_agent._SPAM_RE.search(title), f"spam not caught: {title}"
    for title in legit:
        assert not devto_agent._SPAM_RE.search(title), f"false positive: {title}"


def test_hn_hiring_parse():
    data = json.loads((FIXTURES / "hn_item.json").read_text(encoding="utf-8"))
    items = hn_hiring_agent._items_from_item(data, "Ask HN: Who is hiring? (May 2026)")
    _assert_contract(items)
    for item in items:
        assert item["id"].startswith("hn:")
        assert item["url"].startswith("https://news.ycombinator.com/item?id=")
        assert "<" not in item["text"]  # HTML stripped


def test_stackoverflow_delta(monkeypatch):
    """SO agent computes delta against a prior count and carries the new reading."""

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"total": 2_205_907}

    monkeypatch.setattr(stackoverflow_agent.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(stackoverflow_agent.config, "STACKOVERFLOW_TAGS", ["python"])

    items = stackoverflow_agent.fetch({"python": 2_205_900})
    _assert_contract(items)
    item = items[0]
    assert item["id"].startswith("so:python:")
    assert "delta 7" in item["text"]
    assert item["_so_count"] == {"tag": "python", "total": 2_205_907}


def test_stackoverflow_first_run_has_no_delta(monkeypatch):
    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"total": 100}

    monkeypatch.setattr(stackoverflow_agent.requests, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(stackoverflow_agent.config, "STACKOVERFLOW_TAGS", ["rust"])

    items = stackoverflow_agent.fetch({})  # no prior reading
    assert items[0]["text"].endswith("(delta None)")
