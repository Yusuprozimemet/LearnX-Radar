"""Autonomous skill-alias curation: embeddings propose, an LLM decides, the live
radar uses the result — no human approval gate.

The momentum signal fragments when one rising skill appears under several names
("AI agents" / "Autonomous AI agents"). Exact-name matching misses that, and raw
embedding cosine can't fix it either: it rates genuinely different skills
("PostgreSQL"/"SQLite", "machine learning"/"deep learning") as close as true
variants (experiment, 2026-06-20). So the job is split by what each part is good
at:

  1. embeddings   -> cheaply shortlist name pairs that MIGHT be the same skill
  2. an LLM judge -> decide, with world knowledge, which pairs really are the same
  3. accepted merges become learned SKILL_ALIASES the scorer/extractor pick up

The judge is told to be CONSERVATIVE: when unsure, keep separate. The asymmetry is
deliberate — a wrong merge silently distorts momentum, persists (aliases are
sticky), and waits to be noticed; a missed merge only costs a little signal for a
few days and self-heals next run. Every decision is returned for logging, so a
human stays ON the loop (audit + one-line revert) without being IN it (no approval
blocks the daily lesson).

Pure and injectable: `curate` takes the history, an embedder, and a chat_fn and
returns decisions — no IO, no network of its own. scripts/curate_aliases.py wires
it to real data, the NIM LLM, persistence, the decision log, and the Telegram ping.
"""
from __future__ import annotations

from collections.abc import Callable

from learnx.llm import parse_json_response
from radar.semantic_match import Embedder, cosine, lexical_embedder
from radar.skill_extractor import _canonical

ChatFn = Callable[..., str]


def _vocabulary(history: dict) -> tuple[list[str], dict[str, int]]:
    """Distinct canonical skill names (first-seen order) + days-seen count each.

    Canonicalizing here means any pair the current alias map already collapses
    shares a canonical and so can never be re-proposed."""
    freq: dict[str, int] = {}
    order: list[str] = []
    for day in sorted(history):
        for row in history[day].get("scored", []):
            name = str(row.get("skill", "")).strip()
            if not name:
                continue
            canon = _canonical(name)
            if canon not in freq:
                order.append(canon)
            freq[canon] = freq.get(canon, 0) + 1
    return order, freq


def candidate_pairs(
    history: dict, *, embedder: Embedder = lexical_embedder, threshold: float = 0.6
) -> list[tuple[float, str, str]]:
    """Name pairs whose embeddings are within `threshold` — the judge's shortlist.

    Sorted most-similar first. This is a recall step: it should over-include
    (the LLM rejects the false ones), not try to be precise on its own."""
    vocab, _ = _vocabulary(history)
    vectors = {}
    for i in range(0, len(vocab), 32):
        chunk = vocab[i : i + 32]
        for name, vec in zip(chunk, embedder(chunk), strict=True):
            vectors[name] = vec
    pairs: list[tuple[float, str, str]] = []
    for i in range(len(vocab)):
        for j in range(i + 1, len(vocab)):
            a, b = vocab[i], vocab[j]
            score = cosine(vectors[a], vectors[b])
            if score >= threshold:
                pairs.append((score, a, b))
    pairs.sort(reverse=True)
    return pairs


_SYSTEM = (
    "You curate a controlled vocabulary of software-developer skill names for a "
    "learning radar. You decide, for candidate name pairs, whether the two names "
    "denote the SAME skill (variants/abbreviations/spellings of one thing) and "
    "should be merged, or DIFFERENT skills that must stay separate.\n\n"
    "Be CONSERVATIVE. Merge ONLY names a developer would agree are the same skill "
    "(e.g. 'k8s' = 'Kubernetes', 'AI agents' = 'Autonomous AI agents'). Keep "
    "SEPARATE anything with a real distinction even when topically close: "
    "different tools/libraries ('PostgreSQL' vs 'SQLite'), different languages "
    "('Rust async' vs 'Python asyncio'), or a sub-topic vs its parent ('LLM' vs "
    "'LLM training'). When unsure, keep them separate — a wrong merge is worse "
    "than a missed one.\n\n"
    "Reply with ONLY a JSON array, one object per pair, in the same order:\n"
    '[{"a": "...", "b": "...", "merge": true, "canonical": "<a or b: the more '
    'standard/established name to keep>", "reason": "<short>"}]'
)


def _build_messages(pairs: list[tuple[float, str, str]], freq: dict[str, int]) -> list[dict]:
    lines = []
    for _score, a, b in pairs:
        lines.append(f'- "{a}" (seen {freq.get(a, 0)}d)  vs  "{b}" (seen {freq.get(b, 0)}d)')
    user = "Candidate pairs:\n" + "\n".join(lines)
    return [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": user}]


def judge(
    pairs: list[tuple[float, str, str]], freq: dict[str, int], *, chat_fn: ChatFn
) -> list[dict]:
    """Ask the LLM to rule on each candidate pair. Returns one decision dict per
    VALID reply item: {a, b, merge, canonical, reason, cosine}. Malformed or
    out-of-vocabulary items are dropped (treated as 'no merge' — conservative)."""
    if not pairs:
        return []
    score_by_pair = {frozenset((a, b)): s for s, a, b in pairs}
    raw = chat_fn(_build_messages(pairs, freq), temperature=0.0)
    parsed = parse_json_response(raw)
    if not isinstance(parsed, list):
        return []
    decisions: list[dict] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        a, b = _canonical(str(item.get("a", ""))), _canonical(str(item.get("b", "")))
        key = frozenset((a, b))
        if a == b or key not in score_by_pair:
            continue  # hallucinated or already-merged pair
        merge = bool(item.get("merge"))
        canon = _canonical(str(item.get("canonical", "")))
        if merge and canon not in (a, b):
            continue  # canonical must be one of the pair; otherwise reject the merge
        decisions.append({
            "a": a, "b": b, "merge": merge,
            "canonical": canon if merge else None,
            "reason": str(item.get("reason", "")).strip(),
            "cosine": round(score_by_pair[key], 3),
        })
    return decisions


def aliases_from(decisions: list[dict]) -> dict[str, str]:
    """The {variant -> canonical} map for accepted merges only (drops self-maps)."""
    out: dict[str, str] = {}
    for d in decisions:
        if d["merge"] and d["canonical"]:
            variant = d["b"] if d["canonical"] == d["a"] else d["a"]
            if variant != d["canonical"]:
                out[variant] = d["canonical"]
    return out


def curate(
    history: dict,
    *,
    chat_fn: ChatFn,
    embedder: Embedder = lexical_embedder,
    threshold: float = 0.6,
) -> dict:
    """Full pipeline (no IO): shortlist -> judge -> learned aliases + decision log.

    Returns {"decisions": [...], "aliases": {variant: canonical}}. The caller
    persists the aliases, appends the decisions to the audit log, and notifies."""
    _vocab, freq = _vocabulary(history)
    pairs = candidate_pairs(history, embedder=embedder, threshold=threshold)
    decisions = judge(pairs, freq, chat_fn=chat_fn)
    return {"decisions": decisions, "aliases": aliases_from(decisions)}
