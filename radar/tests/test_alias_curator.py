"""Offline tests for autonomous alias curation. The LLM judge is replaced by a
canned chat_fn, so these are hermetic — no key, no network. They prove the
pipeline shape: embeddings shortlist, the judge's verdicts are honored, and only
valid accepted merges become aliases (hallucinated/invalid items are dropped)."""
import json

from radar import alias_curator
from radar.semantic_match import lexical_embedder


def _history(*day_skills):
    """{date: {scored:[{skill,demand_weight}]}} from (day, [names]) pairs."""
    return {
        f"2026-06-{d:02d}": {"scored": [{"skill": s, "demand_weight": 1.0} for s in names]}
        for d, names in day_skills
    }


def test_vocabulary_dedupes_and_counts_days():
    h = _history((1, ["DuckDB", "AI agents"]), (2, ["DuckDB"]))
    vocab, freq = alias_curator._vocabulary(h)
    assert set(vocab) == {"duckdb", "ai agents"}
    assert freq["duckdb"] == 2 and freq["ai agents"] == 1


def test_candidate_pairs_shortlists_near_duplicates():
    h = _history((1, ["AI agents", "Autonomous AI agents", "DuckDB"]))
    pairs = alias_curator.candidate_pairs(h, embedder=lexical_embedder, threshold=0.6)
    flat = {frozenset((a, b)) for _s, a, b in pairs}
    assert frozenset(("ai agents", "autonomous ai agents")) in flat   # variants shortlisted
    assert frozenset(("duckdb", "ai agents")) not in flat             # unrelated excluded


def test_settled_alias_is_not_reproposed(monkeypatch):
    # Once a pair is a learned alias in the live map (curate applies it before
    # judging, like the daily radar), _canonical collapses both names to one vocab
    # entry, so the judge can't re-rule — and re-flip — a merge that already settled.
    import config
    monkeypatch.setattr(config, "SKILL_ALIASES", {"autonomous ai agents": "ai agents"})
    h = _history((1, ["AI agents", "Autonomous AI agents"]), (2, ["AI agents"]))
    vocab, _freq = alias_curator._vocabulary(h)
    assert vocab == ["ai agents"]                                   # both collapsed -> one
    assert alias_curator.candidate_pairs(h, threshold=0.6) == []   # nothing to re-judge


def test_denylist_pairs_are_never_proposed():
    h = _history((1, ["AI agents", "Autonomous AI agents"]))
    deny = {frozenset(("ai agents", "autonomous ai agents"))}
    pairs = alias_curator.candidate_pairs(h, threshold=0.6, denylist=deny)
    assert pairs == []   # the one close pair is denylisted -> nothing to judge


def test_curate_skips_denylisted_pair():
    h = _history((1, ["AI agents", "Autonomous AI agents"]), (2, ["AI agents"]))
    deny = {frozenset(("ai agents", "autonomous ai agents"))}
    # Even if the judge would say merge, a denylisted pair never reaches it.
    chat = _canned([{"a": "ai agents", "b": "autonomous ai agents", "merge": True,
                     "canonical": "ai agents", "reason": "x"}])
    out = alias_curator.curate(h, chat_fn=chat, threshold=0.6, denylist=deny)
    assert out["aliases"] == {}
    assert out["decisions"] == []


def _canned(decisions):
    """A chat_fn that ignores the prompt and returns a fixed decision list as JSON."""
    return lambda messages, **kw: json.dumps(decisions)


def test_judge_honors_merge_and_keep_verdicts():
    # Hand-built shortlist so the judge test is independent of the embedder: the
    # point is that the LLM's verdict is honored, including a "keep separate" on a
    # pair embeddings flagged (PostgreSQL/SQLite — close topic, different skills).
    pairs = [(0.8, "ai agents", "autonomous ai agents"), (0.7, "postgresql", "sqlite")]
    freq = {"ai agents": 2, "autonomous ai agents": 1, "postgresql": 3, "sqlite": 2}
    chat = _canned([
        {"a": "ai agents", "b": "autonomous ai agents", "merge": True,
         "canonical": "ai agents", "reason": "same"},
        {"a": "postgresql", "b": "sqlite", "merge": False, "reason": "different db"},
    ])
    decisions = alias_curator.judge(pairs, freq, chat_fn=chat)
    by_pair = {frozenset((d["a"], d["b"])): d for d in decisions}
    assert by_pair[frozenset(("ai agents", "autonomous ai agents"))]["merge"] is True
    assert by_pair[frozenset(("postgresql", "sqlite"))]["merge"] is False


def test_judge_drops_hallucinated_and_invalid_items():
    pairs = [(0.8, "ai agents", "autonomous ai agents")]
    freq = {"ai agents": 2, "autonomous ai agents": 1}
    chat = _canned([
        # not a real candidate pair -> dropped
        {"a": "redis", "b": "kafka", "merge": True, "canonical": "redis", "reason": "x"},
        # canonical not one of the pair -> merge rejected
        {"a": "ai agents", "b": "autonomous ai agents", "merge": True,
         "canonical": "something else", "reason": "x"},
    ])
    decisions = alias_curator.judge(pairs, freq, chat_fn=chat)
    assert all(d["a"] != "redis" for d in decisions)            # hallucinated pair gone
    # bad canonical -> the whole item is dropped, so nothing merges (conservative).
    assert not any(d["merge"] for d in decisions)
    assert alias_curator.aliases_from(decisions) == {}


def test_aliases_from_maps_variant_to_canonical():
    decisions = [
        {"a": "autonomous ai agents", "b": "ai agents", "merge": True,
         "canonical": "ai agents", "reason": ""},
        {"a": "postgresql", "b": "sqlite", "merge": False, "canonical": None, "reason": ""},
    ]
    assert alias_curator.aliases_from(decisions) == {"autonomous ai agents": "ai agents"}


def test_curate_end_to_end_with_canned_judge():
    # DuckDB is unrelated, so only the variant pair is shortlisted by the embedder;
    # the canned judge merges it and curate emits the learned alias.
    h = _history((1, ["AI agents", "Autonomous AI agents", "DuckDB"]), (2, ["AI agents"]))
    chat = _canned([
        {"a": "ai agents", "b": "autonomous ai agents", "merge": True,
         "canonical": "ai agents", "reason": "same skill"},
    ])
    out = alias_curator.curate(h, chat_fn=chat, threshold=0.6)
    assert out["aliases"] == {"autonomous ai agents": "ai agents"}
    assert any(d["merge"] for d in out["decisions"])


def test_curation_loop_changes_live_momentum(tmp_path, monkeypatch):
    """The whole machine end to end: a learned alias from curate(), once persisted
    and applied, makes the live scorer treat a variant as the same rising skill."""
    import config
    from radar import gap_scorer
    from storage import paths, state

    monkeypatch.setattr(config, "MOMENTUM_ENABLED", True)
    monkeypatch.setattr(config, "MOMENTUM_SEMANTIC_MATCH", False)  # pure alias-driven
    monkeypatch.setattr(config, "SKILL_ALIASES", {})
    monkeypatch.setattr(paths, "LEARNED_ALIASES_FILE", tmp_path / "skill_aliases.json")

    # Prior days mention only "Autonomous AI agents"; today's skill is "AI agents".
    prior = _history((1, ["Autonomous AI agents"]), (2, ["Autonomous AI agents"]))
    # BEFORE: different names, no alias -> looks like a one-day spike.
    assert gap_scorer._momentum("AI agents", 2.0, prior) == config.MOMENTUM_SPIKE_DAMP

    # Curate over history where both names appear, so the pair is shortlisted+judged.
    seen = _history((1, ["Autonomous AI agents"]), (2, ["AI agents", "Autonomous AI agents"]))
    chat = _canned([{"a": "ai agents", "b": "autonomous ai agents", "merge": True,
                     "canonical": "ai agents", "reason": "same"}])
    out = alias_curator.curate(seen, chat_fn=chat, threshold=0.6)
    state.save_learned_aliases(out["aliases"])
    assert state.apply_learned_aliases() == 1  # merged into the live alias map

    # AFTER: the variant now canonicalizes to today's skill -> boosted, not damped.
    assert gap_scorer._momentum("AI agents", 2.0, prior) > 1.0
