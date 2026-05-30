"""Offline tests for the radar. gap_scorer is pure; the LLM stages are tested
with a canned chat_fn so no network is touched."""
import json
from datetime import date, timedelta

from radar import brief_writer, gap_scorer, skill_extractor

EMPTY_MEMORY = {"version": 1, "skills": {}}


def _ago(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


# --- gap_scorer (pure) -------------------------------------------------------

def test_job_market_outranks_buzz():
    """A skill seen only in HN Hiring (2.0) beats one seen in two dev.to posts."""
    mentions = [
        {"skill": "DuckDB", "sources": ["dev.to", "dev.to"], "evidence": ""},
        {"skill": "Kafka", "sources": ["HN Hiring"], "evidence": ""},
    ]
    ranked = gap_scorer.score(mentions, EMPTY_MEMORY)
    assert ranked[0]["skill"] == "Kafka"
    # dev.to is deduped to one distinct source → weight 0.5
    duck = next(s for s in ranked if s["skill"] == "DuckDB")
    assert duck["demand_weight"] == 0.5
    assert duck["frequency"] == 1


def test_cross_source_adds_up():
    mentions = [{"skill": "Rust", "sources": ["HN Hiring", "Stack Overflow", "dev.to"]}]
    ranked = gap_scorer.score(mentions, EMPTY_MEMORY)
    assert ranked[0]["demand_weight"] == 2.0 + 1.5 + 0.5
    assert ranked[0]["frequency"] == 3


def test_just_taught_is_suppressed():
    """Taught today → ~0 novelty → won't be re-picked."""
    memory = {"skills": {"Kafka": {"times_taught": 1, "last_taught": _ago(0)}}}
    s = gap_scorer.score([{"skill": "Kafka", "sources": ["HN Hiring"]}], memory)[0]
    assert s["novelty"] == 0.0
    assert s["score"] == 0.0
    assert s["suggested_difficulty"] == "intermediate"  # taught once → next is intermediate


def test_resurfaces_after_interval_at_higher_difficulty():
    """Taught once, 8 days ago (interval 7) → fully due again, now intermediate."""
    memory = {"skills": {"Kafka": {"times_taught": 1, "last_taught": _ago(8)}}}
    s = gap_scorer.score([{"skill": "Kafka", "sources": ["HN Hiring"]}], memory)[0]
    assert s["novelty"] == 1.0
    assert s["suggested_difficulty"] == "intermediate"


def test_interval_widens_with_repetition():
    """Same 8-day gap: taught once (interval 7) is fully due; taught twice (14) isn't."""
    once = {"skills": {"K": {"times_taught": 1, "last_taught": _ago(8)}}}
    twice = {"skills": {"K": {"times_taught": 2, "last_taught": _ago(8)}}}
    n_once = gap_scorer.score([{"skill": "K", "sources": ["dev.to"]}], once)[0]["novelty"]
    n_twice = gap_scorer.score([{"skill": "K", "sources": ["dev.to"]}], twice)[0]["novelty"]
    assert n_once == 1.0
    assert n_twice == 8 / 14  # interval doubled
    assert n_twice < n_once


def test_taught_but_missing_date_is_due():
    memory = {"skills": {"Kafka": {"times_taught": 1}}}  # no last_taught
    s = gap_scorer.score([{"skill": "Kafka", "sources": ["HN Hiring"]}], memory)[0]
    assert s["novelty"] == 1.0


def test_unseen_skill_is_beginner_full_novelty():
    s = gap_scorer.score([{"skill": "New", "sources": ["dev.to"]}], EMPTY_MEMORY)[0]
    assert s["novelty"] == 1.0
    assert s["suggested_difficulty"] == "beginner"


def test_tie_break_is_deterministic():
    mentions = [
        {"skill": "Zebra", "sources": ["dev.to"]},
        {"skill": "Alpha", "sources": ["dev.to"]},
    ]
    ranked = gap_scorer.score(mentions, EMPTY_MEMORY)
    # equal score + frequency → alphabetical
    assert [s["skill"] for s in ranked] == ["Alpha", "Zebra"]


def test_table_stakes_sink_below_emerging():
    """A ubiquitous skill in all 4 sources loses to a niche skill in two sources."""
    mentions = [
        {"skill": "Python", "sources": ["HN Hiring", "Stack Overflow", "GitHub Trending", "dev.to"]},
        {"skill": "DuckDB", "sources": ["GitHub Trending", "dev.to"]},
    ]
    ranked = gap_scorer.score(mentions, EMPTY_MEMORY)
    assert ranked[0]["skill"] == "DuckDB"  # 1.5 beats Python's 5.0 * 0.1 = 0.5
    python = next(s for s in ranked if s["skill"] == "Python")
    assert python["table_stakes"] is True
    assert python["score"] == 5.0 * 0.1


def test_table_stakes_match_is_exact_and_normalized():
    # "Python asyncio" is specific → not penalized; "python" (any case) → penalized
    ranked = gap_scorer.score(
        [
            {"skill": "Python asyncio", "sources": ["dev.to"]},
            {"skill": "PYTHON", "sources": ["dev.to"]},
        ],
        EMPTY_MEMORY,
    )
    by_skill = {s["skill"]: s for s in ranked}
    assert by_skill["Python asyncio"]["table_stakes"] is False
    assert by_skill["PYTHON"]["table_stakes"] is True


def test_empty_inputs():
    assert gap_scorer.score([], EMPTY_MEMORY) == []
    assert gap_scorer.top([]) is None


# --- skill_extractor ---------------------------------------------------------

def test_build_digest_caps_text():
    items = [{"source": "dev.to", "title": "T", "text": "x" * 500}]
    line = skill_extractor._build_digest(items)
    assert line.startswith("[dev.to] T :: ")
    assert "x" * 200 in line and "x" * 201 not in line


def test_clean_drops_empty_and_caps(monkeypatch):
    monkeypatch.setattr(skill_extractor.config, "MAX_SKILL_MENTIONS", 2)
    raw = [
        {"skill": "A", "sources": ["HN Hiring"], "evidence": "e"},
        {"skill": "", "sources": ["dev.to"]},  # dropped: empty skill
        {"skill": "B", "sources": []},
        {"skill": "C", "sources": ["dev.to"]},  # dropped: over cap of 2
    ]
    cleaned = skill_extractor._clean(raw)
    assert [m["skill"] for m in cleaned] == ["A", "B"]


def test_extract_with_canned_llm():
    canned = json.dumps(
        [{"skill": "DuckDB", "sources": ["dev.to"], "evidence": "fast OLAP"}]
    )
    items = [{"source": "dev.to", "title": "DuckDB rocks", "text": "columnar"}]
    out = skill_extractor.extract(items, chat_fn=lambda *a, **k: canned)
    assert out == [{"skill": "DuckDB", "sources": ["dev.to"], "evidence": "fast OLAP"}]


def test_extract_salvages_truncated_json():
    """A reply cut off mid-array (the real failure mode) recovers whole objects."""
    truncated = (
        '```json\n[\n'
        '  {"skill": "DuckDB", "sources": ["dev.to"], "evidence": "fast OLAP"},\n'
        '  {"skill": "Kafka", "sources": ["HN Hiring"], "evidence": "queues"},\n'
        '  {"skill": "Rust", "sources": ["GitHub Trending"], "evidence": "Surfaced as a tre'
    )
    items = [{"source": "dev.to", "title": "t", "text": "x"}]
    out = skill_extractor.extract(items, chat_fn=lambda *a, **k: truncated)
    assert [m["skill"] for m in out] == ["DuckDB", "Kafka"]  # partial Rust dropped


def test_extract_empty_items_no_call():
    # chat_fn that would explode proves no call is made on empty input
    def boom(*a, **k):
        raise AssertionError("should not call LLM")

    assert skill_extractor.extract([], chat_fn=boom) == []


# --- brief_writer ------------------------------------------------------------

def test_prior_context_empty_then_bridges_related():
    assert brief_writer._prior_context(EMPTY_MEMORY, "Kafka") == ""
    memory = {"skills": {
        "Async I/O": {"summary": "non-blocking concurrency"},
        "Kafka": {"summary": "log-based streaming"},  # the current skill — excluded
    }}
    ctx = brief_writer._prior_context(memory, "Kafka")
    assert "PREVIOUSLY TAUGHT" in ctx
    assert "Async I/O" in ctx and "non-blocking concurrency" in ctx
    assert "Kafka:" not in ctx  # current skill not offered as its own bridge
    assert "genuinely related to Kafka" in ctx


def test_write_passes_fields_to_prompt():
    captured = {}

    def fake_chat(messages, **k):
        captured["prompt"] = messages[0]["content"]
        return "# DuckDB\n## Why...\n"

    skill = {"skill": "DuckDB", "evidence": "fast OLAP", "sources": ["dev.to"]}
    out = brief_writer.write(skill, EMPTY_MEMORY, chat_fn=fake_chat)
    assert out.startswith("# DuckDB")
    assert "DuckDB" in captured["prompt"] and "fast OLAP" in captured["prompt"]
