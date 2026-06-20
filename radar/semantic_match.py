"""In-memory semantic skill matching (v7 day26 "vectordb", prototype).

Today two skill names are "the same" only if `_canonical` says so: lowercase +
a hand-maintained `config.SKILL_ALIASES` dict (k8s->kubernetes, rsc->react
server components, ...). That has two costs: every new abbreviation needs a
manual alias, and genuine synonyms nobody thought to alias ("Postgres" vs
"PostgreSQL", "GH Actions" vs "GitHub Actions") stay split — which fragments the
momentum signal, since a skill that's really rising looks like two thinner ones.

This adds a second matching tier: represent each skill name as a vector and
match by cosine similarity, so close names collapse without a hand-written
alias. It is deliberately NOT a database — the skill vocabulary is tens of
names, so an in-process dict {canonical: vector} + cosine is faster and simpler
than any vector DB, and it disappears when the process exits (no infra, no
creds). Swap in a real store only if this vocabulary ever grows by orders of
magnitude.

Tiers, cheapest first:
  1. exact canonical / alias match     -> score 1.0   (free, offline, unchanged)
  2. embedding cosine >= threshold     -> semantic match

The embedder is pluggable: any `Callable[[list[str]], list[Vector]]`. The
default `lexical_embedder` is pure-Python and offline (character trigrams +
whole tokens) — it catches abbreviations, spelling and word-order variants
deterministically, which is what tests and the cron can rely on. For true
synonym matching, pass `nim_embedder()` to back it with NVIDIA NIM embeddings.
Either way every name is embedded once and cached in-process.
"""
from __future__ import annotations

import math
import re
from collections.abc import Callable
from functools import lru_cache

from radar.skill_extractor import _canonical

# A vector is sparse: {feature -> weight}. Keys are strings (lexical features)
# or ints (dense-embedding dimensions); cosine only needs hashable keys, so the
# same code serves both backends.
Vector = dict[object, float]
Embedder = Callable[[list[str]], list[Vector]]

_WORD = re.compile(r"[a-z0-9]+")


def cosine(a: Vector, b: Vector) -> float:
    """Cosine similarity of two sparse vectors. 0.0 if either is empty."""
    if not a or not b:
        return 0.0
    # Iterate the smaller dict for the dot product.
    small, large = (a, b) if len(a) <= len(b) else (b, a)
    dot = sum(w * large.get(k, 0.0) for k, w in small.items())
    if dot == 0.0:
        return 0.0
    na = math.sqrt(sum(w * w for w in a.values()))
    nb = math.sqrt(sum(w * w for w in b.values()))
    return dot / (na * nb)


def _trigrams(token: str) -> list[str]:
    """Character trigrams of a single token, padded so short tokens still hash.

    Padding ('$$react$') makes word boundaries features in their own right, so
    'react' and 'reactive' share inner trigrams but differ on the edges.
    """
    t = f"$${token}$"
    return [t[i : i + 3] for i in range(len(t) - 2)]


@lru_cache(maxsize=8192)
def _embed_one_lexical(text: str) -> Vector:
    """Lexical vector for one string, memoized — the skill vocabulary is small
    and re-queried often (once per skill-pair in the momentum hot path), so each
    distinct name is vectorized at most once per process. The returned dict is
    treated as read-only by all callers (cosine and the store never mutate it)."""
    v: Vector = {}
    for tok in _WORD.findall(text.lower()):
        v[("tok", tok)] = v.get(("tok", tok), 0.0) + 2.0
        for g in _trigrams(tok):
            v[("tri", g)] = v.get(("tri", g), 0.0) + 1.0
    return v


def lexical_embedder(texts: list[str]) -> list[Vector]:
    """Offline, deterministic embedder: whole tokens + character trigrams.

    Whole tokens give exact word-overlap weight (so 'react server components'
    strongly matches 'react components'); trigrams give sub-word similarity (so
    'postgres'~'postgresql', 'kubernetes'~'kubernetes cluster'). Tokens are
    weighted higher than trigrams because a shared whole word is stronger
    evidence than a shared fragment. No network, no model, same answer every run.
    """
    return [_embed_one_lexical(t) for t in texts]


def similar(
    a: str, b: str, *, threshold: float, embedder: Embedder = lexical_embedder
) -> bool:
    """Are two skill names the same skill? Exact canonical match, or cosine >=
    threshold under `embedder`. This is the stateless entry point for the scoring
    hot path; with the default lexical embedder it is pure, offline, and (via the
    memo above) cheap to call across every prior-day row. Pass a batching
    embedder like nim_embedder() only for offline analysis, not per-pair here."""
    ca, cb = _canonical(a), _canonical(b)
    if ca == cb:
        return True
    va, vb = embedder([ca, cb])
    return cosine(va, vb) >= threshold


def nim_embedder(
    *, model: str = "nvidia/nv-embedqa-e5-v5", input_type: str = "query"
) -> Embedder:
    """Real-embedding backend via NVIDIA NIM (OpenAI-compatible /embeddings).

    Returns a closure so the OpenAI client is built lazily and the API key is
    only needed if this backend is actually used. NIM retrieval models want an
    `input_type` ("query"/"passage"); we embed every skill name the same way so
    they share one space. Dense vectors are returned as {dim_index: value}.
    """
    def embed(texts: list[str]) -> list[Vector]:
        from openai import OpenAI

        import config

        client = OpenAI(api_key=config.NVIDIA_API_KEY, base_url=config.NVIDIA_BASE_URL)
        resp = client.embeddings.create(
            model=model, input=texts, extra_body={"input_type": input_type}
        )
        return [dict(enumerate(d.embedding)) for d in resp.data]

    return embed


class SemanticMatcher:
    """In-memory vector store + matcher over a small skill vocabulary.

    Add canonical skill names with `add`/`add_many` (each embedded once, cached);
    then `find` returns the closest known skill to a query name, or None if the
    best cosine is below `threshold`. Exact canonical/alias matches short-circuit
    to score 1.0 without touching the embedder, so the common case stays free.
    """

    def __init__(self, embedder: Embedder = lexical_embedder, *, threshold: float = 0.6):
        self._embedder = embedder
        self.threshold = threshold
        self._vectors: dict[str, Vector] = {}  # canonical -> vector (the store)

    def add(self, skill: str) -> str:
        """Add one skill; returns its canonical form. No-op if already present."""
        canon = _canonical(skill)
        if canon not in self._vectors:
            self._vectors[canon] = self._embedder([canon])[0]
        return canon

    def add_many(self, skills: list[str]) -> None:
        """Add several skills in one embedder call (batches the network round-trip)."""
        missing = []
        seen = set()
        for s in skills:
            c = _canonical(s)
            if c not in self._vectors and c not in seen:
                missing.append(c)
                seen.add(c)
        if missing:
            for canon, vec in zip(missing, self._embedder(missing), strict=True):
                self._vectors[canon] = vec

    def find(self, skill: str) -> tuple[str, float] | None:
        """Closest known skill to `skill`, or None if below threshold.

        Tier 1: exact canonical/alias hit -> (canon, 1.0), no embedding.
        Tier 2: highest-cosine known skill, if it clears `threshold`.
        """
        canon = _canonical(skill)
        if canon in self._vectors:
            return canon, 1.0
        if not self._vectors:
            return None
        qvec = self._embedder([canon])[0]
        best, best_score = None, 0.0
        for known, vec in self._vectors.items():
            s = cosine(qvec, vec)
            if s > best_score:
                best, best_score = known, s
        if best is not None and best_score >= self.threshold:
            return best, best_score
        return None

    def __len__(self) -> int:
        return len(self._vectors)
