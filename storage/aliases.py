"""skill_aliases.json + denylist : aliases learned by alias_curator (v7 day26).

Embeddings shortlist name pairs, an LLM judges them, and accepted merges land in
skill_aliases.json. apply_learned_aliases() folds them into the live
config.SKILL_ALIASES at startup so the scorer/extractor collapse the same
variants the hand-written map does. The denylist records pairs a human reverted
("keep separate") so the weekly loop can't re-merge an overruled decision.
"""
import json

import config
from storage import paths


def load_learned_aliases() -> dict[str, str]:
    """{variant -> canonical} aliases the curator has accepted so far. Empty when
    the file is missing/corrupt — the radar then runs on the hand-written map only."""
    if not paths.LEARNED_ALIASES_FILE.exists():
        return {}
    try:
        data = json.loads(paths.LEARNED_ALIASES_FILE.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def flatten_aliases(mapping: dict[str, str]) -> dict[str, str]:
    """Collapse alias chains so every value is a TERMINAL canonical — one that is
    never itself a key. The curator judges name pairs independently, so a single
    run can accept both `a -> b` and `b -> c`; single-hop _canonical would then
    resolve `a -> b` but leave `b -> c` unjoined, refragmenting the very skill the
    merge was meant to unify (the 2026-06-22 run did exactly this with
    `agentic ai -> ai agents -> autonomous ai agents`). Idempotent and chain-free
    maps pass through unchanged. A contradictory cycle (`a -> b -> a`, from opposite
    verdicts) is broken by dropping the looping entries — the names stay separate,
    which is the conservative outcome and shows up in the audit log for a human."""
    out: dict[str, str] = {}
    for variant in mapping:
        seen = {variant}
        canon = mapping[variant]
        while canon in mapping and canon not in seen:
            seen.add(canon)
            canon = mapping[canon]
        if canon != variant:  # drop self/cyclic maps; a real alias points elsewhere
            out[variant] = canon
    return out


def save_learned_aliases(aliases: dict[str, str]) -> None:
    # Flatten on write so the committed file never carries a chain, even when one
    # forms across runs (run N learns `a -> b`, run N+1 learns `b -> c`).
    paths.ensure_parent(paths.LEARNED_ALIASES_FILE).write_text(
        json.dumps(flatten_aliases(aliases), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def apply_learned_aliases() -> int:
    """Merge learned aliases into the live config.SKILL_ALIASES so _canonical sees
    them everywhere. Hand-written entries win on conflict. Returns how many learned
    aliases were added. Call once at startup, before any scoring."""
    learned = load_learned_aliases()
    added = 0
    for variant, canon in learned.items():
        if variant not in config.SKILL_ALIASES:
            config.SKILL_ALIASES[variant] = canon
            added += 1
    # Collapse any chain in the combined map — including a learned value that points
    # at a hand-written key — so single-hop _canonical resolves every variant in one
    # step. Mutates in place to keep the same dict other modules already reference.
    config.SKILL_ALIASES.update(flatten_aliases(config.SKILL_ALIASES))
    return added


def load_alias_denylist() -> set[frozenset[str]]:
    """Canonical name-pairs a human ruled 'keep separate'. The curator skips these
    so a reverted merge is never re-proposed (the loop can't undo your override).
    Stored as a list of [a, b] pairs; returned as a set of frozensets for lookup."""
    if not paths.ALIAS_DENYLIST_FILE.exists():
        return set()
    try:
        data = json.loads(paths.ALIAS_DENYLIST_FILE.read_text(encoding="utf-8"))
        return {frozenset((str(a), str(b))) for a, b in data}
    except (json.JSONDecodeError, OSError, ValueError):
        return set()


def save_alias_denylist(pairs: set[frozenset[str]]) -> None:
    paths.ensure_parent(paths.ALIAS_DENYLIST_FILE).write_text(
        json.dumps(sorted(sorted(p) for p in pairs), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
