"""Offline tests for the vendored brief-grounding helpers (radar/research).

No network: web._clean is a pure parser, exa.search short-circuits without a key,
and filter_relevant/format_context are pure.
"""
import json

import config
from radar.research import exa, filter_relevant, format_context, web


def test_web_clean_strips_jina_header_and_boilerplate():
    raw = (
        "Title: DuckDB Docs\n"
        "URL Source: https://duckdb.org\n"
        "Markdown Content:\n"
        "DuckDB is an in-process OLAP database.\n"
        "No contributions on June 1st. No contributions on June 2nd.\n"
        "Warning: target server returned 999\n"
    )
    title, body = web._clean(raw)
    assert title == "DuckDB Docs"
    assert "in-process OLAP" in body
    assert "contributions on June" not in body  # GH calendar collapsed
    assert "Warning:" not in body               # Jina diagnostic dropped


def test_web_clean_blocked_page_is_empty():
    # Only a header + diagnostics, no real body → empty so caller drops it.
    _, body = web._clean("Title: x\nMarkdown Content:\nWarning: blocked\n")
    assert body == ""


def test_exa_search_no_key_returns_empty(monkeypatch):
    monkeypatch.setattr(config, "EXA_API_KEY", None)
    assert exa.search("DuckDB") == []


def test_exa_search_parses_results(monkeypatch):
    monkeypatch.setattr(config, "EXA_API_KEY", "k")
    payload = {
        "results": [
            {"url": "https://a.com", "title": "A", "highlights": ["snip one", "snip two"]},
            {"url": "https://b.com", "title": "B", "text": "full text"},
        ]
    }

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps(payload).encode()

    monkeypatch.setattr(exa.urllib.request, "urlopen", lambda *a, **k: _Resp())
    items = exa.search("DuckDB", limit=5)
    assert [i["id"] for i in items] == ["exa:https://a.com", "exa:https://b.com"]
    assert items[0]["source"] == "Exa Web"
    assert items[0]["text"] == "snip one\nsnip two"   # highlights joined
    assert items[1]["text"] == "full text"            # falls back to text


def test_filter_relevant_ranks_by_coverage():
    items = [
        {"title": "cats", "text": "nothing here", "url": "u1"},
        {"title": "DuckDB OLAP", "text": "DuckDB analytics engine", "url": "u2"},
    ]
    ranked = filter_relevant("DuckDB OLAP analytics", items, keep=5)
    assert ranked[0]["url"] == "u2"


def test_filter_relevant_no_terms_preserves_order():
    items = [{"title": "a", "text": "", "url": "u1"}, {"title": "b", "text": "", "url": "u2"}]
    assert filter_relevant("of to in", items, keep=5) == items  # all stopwords → input order


def test_format_context_numbers_blocks():
    items = [{"source": "HN", "title": "T", "url": "http://x", "text": "body text here"}]
    ctx = format_context(items, text_chars=4)
    assert ctx.startswith("[1] HN — T")
    assert "URL: http://x" in ctx
    assert "body" in ctx and "body text" not in ctx  # text capped at 4 chars
