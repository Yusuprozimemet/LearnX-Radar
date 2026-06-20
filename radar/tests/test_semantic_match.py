"""Offline tests for the in-memory semantic skill matcher.

The matcher core is pure (cosine over sparse vectors) and the default embedder
is the deterministic lexical one, so these need no network and no API key. A
tiny stub embedder is used where we want to assert the tiering/threshold logic
independently of any particular vectorization.
"""
from radar.semantic_match import (
    SemanticMatcher,
    cosine,
    lexical_embedder,
    nim_embedder,
    similar,
)


def test_cosine_basics():
    assert cosine({"a": 1.0}, {"a": 1.0}) == 1.0          # identical
    assert cosine({"a": 1.0}, {"b": 1.0}) == 0.0          # orthogonal
    assert cosine({}, {"a": 1.0}) == 0.0                  # empty -> 0, no div-by-zero
    # 45 degrees: shares one of two equal components.
    assert abs(cosine({"a": 1.0, "b": 1.0}, {"a": 1.0}) - 0.7071) < 1e-3


def test_exact_and_alias_hits_short_circuit():
    m = SemanticMatcher()
    m.add("Kubernetes")
    # exact (case/space-insensitive via _canonical)
    assert m.find("  kubernetes ") == ("kubernetes", 1.0)
    # alias from config.SKILL_ALIASES (k8s -> kubernetes) resolves to the same node
    assert m.find("k8s") == ("kubernetes", 1.0)


def test_lexical_matches_spelling_variants_not_in_alias_map():
    m = SemanticMatcher(lexical_embedder, threshold=0.5)
    m.add("GitHub Actions")
    # Not aliased anywhere; singular/plural variant shares 'github' + most
    # 'action(s)' trigrams, so the lexical embedder folds it in below 1.0.
    hit = m.find("GitHub Action")
    assert hit is not None and hit[0] == "github actions"
    assert 0.5 <= hit[1] < 1.0


def test_below_threshold_returns_none():
    m = SemanticMatcher(lexical_embedder, threshold=0.6)
    m.add("Kubernetes")
    assert m.find("WebAssembly") is None   # unrelated names must not merge


def test_empty_store_returns_none():
    assert SemanticMatcher().find("anything") is None


def test_add_many_dedupes_and_batches():
    calls: list[list[str]] = []

    def counting_embedder(texts):
        calls.append(list(texts))
        return lexical_embedder(texts)

    m = SemanticMatcher(counting_embedder)
    m.add_many(["Kubernetes", "k8s", "Kubernetes", "Docker"])
    # k8s->kubernetes and the dup collapse: only kubernetes + docker stored,
    # embedded in a single batched call.
    assert len(m) == 2
    assert len(calls) == 1
    assert sorted(calls[0]) == ["docker", "kubernetes"]


def test_stub_embedder_drives_threshold_logic():
    # Hand-built vectors let us assert the threshold boundary exactly.
    vecs = {
        "alpha": {0: 1.0, 1: 0.0},
        "near": {0: 0.9, 1: 0.1},   # cosine ~0.994 with alpha
        "far": {0: 0.0, 1: 1.0},    # cosine 0.0 with alpha
    }
    m = SemanticMatcher(lambda texts: [vecs[t] for t in texts], threshold=0.6)
    m.add("alpha")
    assert m.find("near")[0] == "alpha"
    assert m.find("far") is None


def test_nim_embedder_is_lazy():
    # Building the backend must not import openai or need a key until called.
    assert callable(nim_embedder())


def test_similar_exact_alias_and_variant():
    # exact canonical
    assert similar("DuckDB", "duckdb", threshold=0.75)
    # alias (k8s -> kubernetes from config.SKILL_ALIASES)
    assert similar("k8s", "Kubernetes", threshold=0.75)
    # real variant folds at the tuned threshold...
    assert similar("AI agents", "Autonomous AI agents", threshold=0.75)
    # ...but unrelated names never merge
    assert not similar("DuckDB", "WebAssembly", threshold=0.75)


def test_similar_threshold_is_respected():
    # The same pair flips with the cutoff: matched at 0.75, rejected near 1.0.
    assert similar("AI agents", "Autonomous AI agents", threshold=0.75)
    assert not similar("AI agents", "Autonomous AI agents", threshold=0.99)
