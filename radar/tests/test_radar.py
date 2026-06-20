"""Offline tests for the radar. gap_scorer is pure; the LLM stages are tested
with a canned chat_fn so no network is touched."""
import json
from datetime import date, timedelta

import pytest

import config
from radar import brief_writer, gap_scorer, skill_extractor

EMPTY_MEMORY = {"version": 1, "skills": {}}


@pytest.fixture(autouse=True)
def _no_live_exa(monkeypatch):
    """Keep grounding tests hermetic — never let _ground hit the live Exa API."""
    monkeypatch.setattr(config, "EXA_API_KEY", None, raising=False)


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
        {
            "skill": "Python",
            "sources": ["HN Hiring", "Stack Overflow", "GitHub Trending", "dev.to"],
        },
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


# --- personalization (v4 / day10) --------------------------------------------

def test_no_profile_is_v3_behavior():
    """profile=None: nothing is personalized, score is the plain v3 formula."""
    s = gap_scorer.score([{"skill": "Redis", "sources": ["HN Hiring"]}], EMPTY_MEMORY)[0]
    assert s["known"] is False
    assert s["goal_match"] is False
    assert s["score"] == 2.0  # demand 2.0 * novelty 1.0, untouched


def test_known_skill_sinks_below_unknown():
    """A skill the user already has loses to an equally-demanded unknown one."""
    profile = {"known": {"Redis"}, "goals": []}
    ranked = gap_scorer.score(
        [
            {"skill": "Redis", "sources": ["HN Hiring"]},
            {"skill": "Pulsar", "sources": ["HN Hiring"]},
        ],
        EMPTY_MEMORY,
        profile,
    )
    assert ranked[0]["skill"] == "Pulsar"
    redis = next(s for s in ranked if s["skill"] == "Redis")
    assert redis["known"] is True
    assert redis["score"] == 2.0 * config.KNOWN_PENALTY


def test_goal_match_outranks_non_goal():
    """A goal-relevant skill beats an equally-demanded skill off your path."""
    profile = {"known": set(), "goals": ["streaming"]}
    ranked = gap_scorer.score(
        [
            {"skill": "Kafka streaming", "sources": ["dev.to"]},
            {"skill": "Webpack", "sources": ["dev.to"]},
        ],
        EMPTY_MEMORY,
        profile,
    )
    assert ranked[0]["skill"] == "Kafka streaming"
    assert ranked[0]["goal_match"] is True
    assert ranked[0]["score"] == 0.5 * config.GOAL_BOOST


def test_goal_match_is_case_insensitive_both_directions():
    assert gap_scorer._goal_match("Rust async", ["RUST"]) is True       # goal in skill
    assert gap_scorer._goal_match("LLM", ["llm agents"]) is True        # skill in goal
    assert gap_scorer._goal_match("Webpack", ["rust", "kafka"]) is False
    assert gap_scorer._goal_match("anything", [""]) is False            # empty goal ignored


def test_known_and_table_stakes_compose():
    """Both penalties apply; score stays non-negative."""
    profile = {"known": {"python"}, "goals": []}
    s = gap_scorer.score([{"skill": "Python", "sources": ["HN Hiring"]}], EMPTY_MEMORY, profile)[0]
    assert s["table_stakes"] is True
    assert s["known"] is True
    assert s["score"] == 2.0 * config.TABLE_STAKES_PENALTY * config.KNOWN_PENALTY
    assert s["score"] >= 0


# --- cross-day momentum (v7 Day 26) ------------------------------------------

def _hist(*day_rows):
    """Build trending_history {date: {scored:[...]}} from (days_ago, rows) pairs."""
    return {_ago(d): {"today_skill": None, "scored": rows} for d, rows in day_rows}


def test_momentum_neutral_when_disabled_or_no_history(monkeypatch):
    # No history -> 1.0 regardless of flag.
    assert gap_scorer._momentum("DuckDB", 2.0, None) == 1.0
    # Flag off -> 1.0 even with history.
    monkeypatch.setattr(config, "MOMENTUM_ENABLED", False)
    h = _hist((1, [{"skill": "DuckDB", "demand_weight": 2.0}]))
    assert gap_scorer._momentum("DuckDB", 2.0, h) == 1.0


def test_momentum_spike_damp_for_today_only(monkeypatch):
    monkeypatch.setattr(config, "MOMENTUM_ENABLED", True)
    # Prior days exist but never mention DuckDB -> one-day spike.
    h = _hist((1, [{"skill": "Other", "demand_weight": 1.0}]),
              (2, [{"skill": "Other", "demand_weight": 1.0}]))
    assert gap_scorer._momentum("DuckDB", 2.0, h) == config.MOMENTUM_SPIKE_DAMP


def test_momentum_boost_scales_with_recurrence_and_acceleration(monkeypatch):
    monkeypatch.setattr(config, "MOMENTUM_ENABLED", True)
    monkeypatch.setattr(config, "MOMENTUM_WINDOW_DAYS", 14)
    monkeypatch.setattr(config, "MOMENTUM_MAX_BOOST", 1.5)
    # Present 2 of 3 prior days, prior avg demand 1.5; today 3.0 -> accelerating.
    h = _hist((1, [{"skill": "DuckDB", "demand_weight": 2.0}]),
              (2, [{"skill": "DuckDB", "demand_weight": 1.0}]),
              (3, [{"skill": "Other", "demand_weight": 1.0}]))
    m = gap_scorer._momentum("DuckDB", 3.0, h)
    assert m == 1.0 + 0.5 * (2 / 3)  # boost scaled by recurrence 2/3, full (accelerating)


def test_momentum_half_boost_when_not_accelerating(monkeypatch):
    monkeypatch.setattr(config, "MOMENTUM_ENABLED", True)
    monkeypatch.setattr(config, "MOMENTUM_MAX_BOOST", 1.5)
    h = _hist((1, [{"skill": "DuckDB", "demand_weight": 2.0}]),
              (2, [{"skill": "DuckDB", "demand_weight": 1.0}]),
              (3, [{"skill": "Other", "demand_weight": 1.0}]))
    full = 1.0 + 0.5 * (2 / 3)
    # today demand 1.0 <= prior avg 1.5 -> half the boost above 1.0
    m = gap_scorer._momentum("DuckDB", 1.0, h)
    assert m == 1.0 + (full - 1.0) * 0.5


def test_momentum_matches_across_days_by_canonical(monkeypatch):
    monkeypatch.setattr(config, "MOMENTUM_ENABLED", True)
    monkeypatch.setattr(config, "SKILL_ALIASES", {"k8s": "kubernetes"})
    # History stored "Kubernetes"; today's skill is "k8s" -> same canonical, counts.
    h = _hist((1, [{"skill": "Kubernetes", "demand_weight": 2.0}]),
              (2, [{"skill": "Kubernetes", "demand_weight": 2.0}]))
    assert gap_scorer._momentum("k8s", 3.0, h) > 1.0


def test_momentum_excludes_today_from_history(monkeypatch):
    monkeypatch.setattr(config, "MOMENTUM_ENABLED", True)
    # Only today in history -> no PRIOR days to judge against -> neutral 1.0.
    only_today = _hist((0, [{"skill": "DuckDB", "demand_weight": 2.0}]))
    assert gap_scorer._momentum("DuckDB", 2.0, only_today) == 1.0
    # Today carries DuckDB but the one PRIOR day doesn't: today must be excluded,
    # so DuckDB has no prior presence -> spike damp (proves today isn't counted).
    h = _hist((0, [{"skill": "DuckDB", "demand_weight": 2.0}]),
              (1, [{"skill": "Other", "demand_weight": 1.0}]))
    assert gap_scorer._momentum("DuckDB", 2.0, h) == config.MOMENTUM_SPIKE_DAMP


def test_score_folds_momentum_in(monkeypatch):
    monkeypatch.setattr(config, "MOMENTUM_ENABLED", True)
    h = _hist((1, [{"skill": "DuckDB", "demand_weight": 0.5}]),
              (2, [{"skill": "DuckDB", "demand_weight": 0.5}]))
    s = gap_scorer.score([{"skill": "DuckDB", "sources": ["dev.to"]}], EMPTY_MEMORY,
                         history=h)[0]
    assert s["momentum"] > 1.0
    assert s["canonical"] == "duckdb"
    assert s["score"] == s["demand_weight"] * s["novelty"] * s["momentum"]


def test_score_without_history_is_unchanged():
    """Back-compat: no history arg -> momentum 1.0, exact pre-Day26 score."""
    s = gap_scorer.score([{"skill": "Redis", "sources": ["HN Hiring"]}], EMPTY_MEMORY)[0]
    assert s["momentum"] == 1.0
    assert s["score"] == 2.0  # demand 2.0 x novelty 1.0, untouched


def test_momentum_folds_semantic_variant(monkeypatch):
    """With semantic matching on, a skill named differently across days still
    feeds one momentum signal (the alias map never had to know the variant)."""
    monkeypatch.setattr(config, "MOMENTUM_ENABLED", True)
    monkeypatch.setattr(config, "MOMENTUM_SEMANTIC_MATCH", True)
    monkeypatch.setattr(config, "MOMENTUM_SEMANTIC_THRESHOLD", 0.75)
    # Prior days call it "Autonomous AI agents"; today it's "AI agents".
    h = _hist((1, [{"skill": "Autonomous AI agents", "demand_weight": 1.0}]),
              (2, [{"skill": "Autonomous AI agents", "demand_weight": 1.0}]))
    assert gap_scorer._momentum("AI agents", 2.0, h) > 1.0  # boosted, not spike-damped


def test_momentum_semantic_off_falls_back_to_exact(monkeypatch):
    """Flag off -> exact-name only, so the same variant looks like a one-day spike."""
    monkeypatch.setattr(config, "MOMENTUM_ENABLED", True)
    monkeypatch.setattr(config, "MOMENTUM_SEMANTIC_MATCH", False)
    h = _hist((1, [{"skill": "Autonomous AI agents", "demand_weight": 1.0}]),
              (2, [{"skill": "Autonomous AI agents", "demand_weight": 1.0}]))
    assert gap_scorer._momentum("AI agents", 2.0, h) == config.MOMENTUM_SPIKE_DAMP


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


def test_extract_single_pass_with_canned_llm(monkeypatch):
    monkeypatch.setattr(skill_extractor.config, "EXTRACTION_MAPREDUCE", False)
    canned = json.dumps(
        [{"skill": "DuckDB", "sources": ["dev.to"], "evidence": "fast OLAP"}]
    )
    items = [{"source": "dev.to", "title": "DuckDB rocks", "text": "columnar"}]
    out = skill_extractor.extract(items, chat_fn=lambda *a, **k: canned)
    assert out == [{"skill": "DuckDB", "sources": ["dev.to"], "evidence": "fast OLAP"}]


def test_extract_single_pass_salvages_truncated_json(monkeypatch):
    """A reply cut off mid-array (the real failure mode) recovers whole objects."""
    monkeypatch.setattr(skill_extractor.config, "EXTRACTION_MAPREDUCE", False)
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


# --- map-reduce extraction (v7 Day 25) ---------------------------------------

def test_term_pattern_word_boundary_and_punctuation():
    """The deterministic matcher must be a token/phrase match, not a substring."""
    go = skill_extractor._term_pattern("go")
    assert go.search("learning go today") and go.search("(go)")
    assert not go.search("going") and not go.search("mongodb") and not go.search("ago")

    phrase = skill_extractor._term_pattern("react server components")
    assert phrase.search("using React  Server   Components now")  # flexible whitespace
    assert not phrase.search("react components")

    cpp = skill_extractor._term_pattern("c++")
    assert cpp.search("we use c++ here")
    assert not cpp.search("c++17") and not cpp.search("abcc++")


def test_canonical_and_alias_merge(monkeypatch):
    monkeypatch.setattr(skill_extractor.config, "SKILL_ALIASES", {"k8s": "kubernetes"})
    assert skill_extractor._canonical("  K8S ") == "kubernetes"
    assert skill_extractor._canonical("Kubernetes") == "kubernetes"
    # Two surface forms across chunks collapse into one group.
    groups = skill_extractor._reduce([
        {"skill": "k8s", "sources": ["HN Hiring"], "evidence": "ops"},
        {"skill": "Kubernetes", "sources": ["dev.to"], "evidence": ""},
    ])
    assert set(groups) == {"kubernetes"}
    assert groups["kubernetes"]["surfaces"] == {"k8s", "Kubernetes"}


def test_attribute_sources_are_deterministic_from_corpus(monkeypatch):
    """Attribution comes from a corpus scan, NOT the LLM's (here wrong) tally."""
    monkeypatch.setattr(skill_extractor.config, "SKILL_ALIASES", {})
    monkeypatch.setattr(skill_extractor.config, "AMBIGUOUS_SHORT_SKILLS", set())
    groups = skill_extractor._reduce(
        [{"skill": "DuckDB", "sources": ["GitHub Trending"], "evidence": "olap"}]
    )
    items = [
        {"source": "HN Front Page", "title": "DuckDB 1.0", "text": "fast"},
        {"source": "dev.to", "title": "why I use duckdb", "text": "columnar"},
        {"source": "Reddit", "title": "cats", "text": "unrelated"},
    ]
    out = skill_extractor._attribute(groups, items)
    m = next(x for x in out if x["skill"] == "DuckDB")
    # Real sources from the scan (HN + dev.to), NOT the LLM's "GitHub Trending".
    assert m["sources"] == ["HN Front Page", "dev.to"]


def test_attribute_alias_surface_matched_in_corpus(monkeypatch):
    """Alias canonical is scanned even if only the alias key appears in the corpus."""
    monkeypatch.setattr(skill_extractor.config, "SKILL_ALIASES", {"k8s": "kubernetes"})
    monkeypatch.setattr(skill_extractor.config, "AMBIGUOUS_SHORT_SKILLS", set())
    groups = skill_extractor._reduce([{"skill": "Kubernetes", "sources": [], "evidence": ""}])
    items = [{"source": "HN Hiring", "title": "k8s operators", "text": "scaling"}]
    out = skill_extractor._attribute(groups, items)
    assert out[0]["sources"] == ["HN Hiring"]  # matched via the k8s alias surface


def test_attribute_ambiguous_skill_falls_back_to_llm_sources(monkeypatch):
    """Short/ambiguous names skip the corpus scan and use the LLM's sources."""
    monkeypatch.setattr(skill_extractor.config, "AMBIGUOUS_SHORT_SKILLS", {"go"})
    groups = skill_extractor._reduce(
        [{"skill": "Go", "sources": ["HN Hiring"], "evidence": "backend"}]
    )
    # A corpus full of "going"/"ago" would false-match a substring scan; ambiguous
    # path must ignore the corpus and trust the LLM-reported source.
    items = [{"source": "Reddit", "title": "going to the store", "text": "ago"}]
    out = skill_extractor._attribute(groups, items)
    assert out[0]["sources"] == ["HN Hiring"]


def test_attribute_falls_back_when_corpus_phrasing_differs(monkeypatch):
    """If the LLM's term isn't found verbatim in the corpus, keep its sources."""
    monkeypatch.setattr(skill_extractor.config, "SKILL_ALIASES", {})
    monkeypatch.setattr(skill_extractor.config, "AMBIGUOUS_SHORT_SKILLS", set())
    groups = skill_extractor._reduce(
        [{"skill": "agentic coding", "sources": ["Lobste.rs"], "evidence": "ai"}]
    )
    items = [{"source": "HN Front Page", "title": "agentic AI workflows", "text": "tools"}]
    out = skill_extractor._attribute(groups, items)  # "agentic coding" not present verbatim
    assert out[0]["sources"] == ["Lobste.rs"]


def test_chunk_by_tokens_splits_and_recall_unions(monkeypatch):
    monkeypatch.setattr(skill_extractor.config, "EXTRACTION_MAPREDUCE", True)
    monkeypatch.setattr(skill_extractor.config, "EXTRACTION_CHUNK_TOKENS", 30)
    monkeypatch.setattr(skill_extractor.config, "SKILL_ALIASES", {})
    monkeypatch.setattr(skill_extractor.config, "AMBIGUOUS_SHORT_SKILLS", set())
    items = [
        {"source": "HN Front Page", "title": "DuckDB benchmarks", "text": "x" * 200},
        {"source": "dev.to", "title": "Kafka consumer groups deepdive", "text": "y" * 200},
    ]
    assert len(skill_extractor._chunk_by_tokens(items, 30)) >= 2  # split into chunks

    # Each chunk returns the skill in its own item. Key off an item-unique word —
    # NOT the skill name, since the extract.txt template itself names DuckDB/Kafka.
    def per_chunk(messages, **k):
        digest = messages[0]["content"]
        if "benchmarks" in digest:
            return json.dumps([{"skill": "DuckDB", "sources": [], "evidence": ""}])
        return json.dumps([{"skill": "Kafka consumer groups", "sources": [], "evidence": ""}])

    out = skill_extractor.extract(items, chat_fn=per_chunk)
    assert {m["skill"] for m in out} == {"DuckDB", "Kafka consumer groups"}


def test_extract_max_candidates_cap(monkeypatch):
    monkeypatch.setattr(skill_extractor.config, "EXTRACTION_MAPREDUCE", True)
    monkeypatch.setattr(skill_extractor.config, "EXTRACTION_MAX_CANDIDATES", 1)
    monkeypatch.setattr(skill_extractor.config, "EXTRACTION_CHUNK_TOKENS", 9999)
    monkeypatch.setattr(skill_extractor.config, "AMBIGUOUS_SHORT_SKILLS", set())
    canned = json.dumps([
        {"skill": "DuckDB", "sources": [], "evidence": ""},
        {"skill": "Kafka", "sources": [], "evidence": ""},
    ])
    items = [{"source": "HN Front Page", "title": "DuckDB and Kafka", "text": "both here"}]
    out = skill_extractor.extract(items, chat_fn=lambda *a, **k: canned)
    assert len(out) == 1  # capped to EXTRACTION_MAX_CANDIDATES


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


def test_action_step_extracts_section():
    brief = (
        "# DuckDB\n## Core ideas\nstuff\n\n"
        "## Do this in 5 minutes\nRun `pip install duckdb` then `duckdb -c \"select 42\"`.\n\n"
        "## Where it fits\nmore"
    )
    action = brief_writer.action_step(brief)
    assert "pip install duckdb" in action
    assert "Core ideas" not in action and "Where it fits" not in action


def test_action_step_missing_section_is_empty():
    assert brief_writer.action_step("# DuckDB\n## Core ideas\nno action here") == ""
    assert brief_writer.action_step("") == ""


def test_write_passes_fields_to_prompt():
    captured = {}

    def fake_chat(messages, **k):
        captured["prompt"] = messages[0]["content"]
        return "# DuckDB\n## Why...\n"

    skill = {"skill": "DuckDB", "evidence": "fast OLAP", "sources": ["dev.to"]}
    out = brief_writer.write(skill, EMPTY_MEMORY, chat_fn=fake_chat)
    assert out.startswith("# DuckDB")
    assert "DuckDB" in captured["prompt"] and "fast OLAP" in captured["prompt"]


# --- brief grounding (v7 Day 24) ---------------------------------------------

_SKILL = {"skill": "DuckDB", "evidence": "fast OLAP engine", "sources": ["HN Hiring"]}
_ITEMS = [
    {"id": "a", "source": "HN Front Page", "title": "DuckDB hits 1.0",
     "url": "http://x/duckdb", "text": "DuckDB OLAP analytics", "meta": ""},
    {"id": "b", "source": "Reddit", "title": "cat pics",
     "url": "http://x/cats", "text": "unrelated fluff", "meta": ""},
]


def test_select_sources_reads_relevant_top_n(monkeypatch):
    monkeypatch.setattr(config, "GROUNDING_READ_TOP_N", 1)
    reads = []

    def fake_reader(url):
        reads.append(url)
        return {"id": "web", "source": "Web", "title": "DuckDB docs",
                "url": url, "text": "DuckDB is an in-process OLAP database.", "meta": "x"}

    sel = brief_writer._select_sources(_SKILL, _ITEMS, reader=fake_reader)
    assert reads == ["http://x/duckdb"]          # read the relevant item, not the cat one
    assert len(sel) == 1
    assert sel[0]["url"] == "http://x/duckdb"
    assert "in-process OLAP" in sel[0]["text"]   # full read content, not the snippet


def test_select_sources_scrubs_fetched_text(monkeypatch):
    monkeypatch.setattr(config, "GROUNDING_READ_TOP_N", 1)

    def leaky_reader(url):
        return {"id": "w", "source": "Web", "title": "t", "url": url,
                "text": "Ask the maintainer at dev@duckdb.org for DuckDB help.", "meta": ""}

    sel = brief_writer._select_sources(_SKILL, _ITEMS, reader=leaky_reader)
    assert "dev@duckdb.org" not in sel[0]["text"] and "[email]" in sel[0]["text"]


def test_select_sources_falls_back_to_snippet_on_read_failure(monkeypatch):
    monkeypatch.setattr(config, "GROUNDING_READ_TOP_N", 1)
    sel = brief_writer._select_sources(_SKILL, _ITEMS, reader=lambda u: None)
    assert sel[0]["text"] == "DuckDB OLAP analytics"  # the original snippet survives
    assert sel[0]["url"] == "http://x/duckdb"


def test_select_sources_empty_when_disabled(monkeypatch):
    monkeypatch.setattr(config, "GROUNDING_ENABLED", False)
    assert brief_writer._select_sources(_SKILL, _ITEMS, reader=lambda u: None) == []


def test_select_sources_empty_when_no_items():
    assert brief_writer._select_sources(_SKILL, [], reader=lambda u: None) == []


def test_sources_section_uses_real_urls_only():
    """The appended Sources list is authored from data — never the LLM's URLs."""
    sel = [{"url": "http://x/duckdb"}, {"url": "http://x/two"}, {"url": ""}]
    section = brief_writer._sources_section(sel)
    assert section.startswith("\n\n## Sources\n")
    assert "1. http://x/duckdb" in section and "2. http://x/two" in section
    assert "3." not in section  # empty-url source skipped
    assert brief_writer._sources_section([]) == ""


def test_write_grounded_appends_real_sources_and_keeps_action(monkeypatch):
    monkeypatch.setattr(config, "GROUNDING_READ_TOP_N", 1)
    monkeypatch.setattr(
        brief_writer.research.web, "read",
        lambda url: {"id": "w", "source": "Web", "title": "DuckDB docs",
                     "url": url, "text": "DuckDB columnar OLAP.", "meta": ""},
    )
    captured = {}

    def fake_chat(messages, **k):
        captured["prompt"] = messages[0]["content"]
        # The LLM tries to fabricate a source URL; our code must NOT use it.
        return ("# DuckDB\n## Do this in 5 minutes\nRun `pip install duckdb`.\n"
                "## Sources\n1. https://hallucinated.example/duckdb")

    out = brief_writer.write(_SKILL, EMPTY_MEMORY, _ITEMS, chat_fn=fake_chat)
    assert "http://x/duckdb" in captured["prompt"]   # grounding reached the prompt
    assert "[n]" in captured["prompt"]               # citation instruction present
    # Deterministic Sources appended from the REAL url; action step still parses
    # (it stops at the appended ## Sources heading).
    assert out.rstrip().endswith("## Sources\n1. http://x/duckdb")
    assert "pip install duckdb" in brief_writer.action_step(out)


def test_write_ungrounded_fallback_uses_placeholder_and_no_sources(monkeypatch):
    captured = {}

    def fake_chat(messages, **k):
        captured["prompt"] = messages[0]["content"]
        return "# DuckDB\n"

    # No items → grounding empty → placeholder injected, no Sources appended.
    out = brief_writer.write(_SKILL, EMPTY_MEMORY, [], chat_fn=fake_chat)
    assert brief_writer._NO_GROUNDING in captured["prompt"]
    assert "## Sources" not in out
