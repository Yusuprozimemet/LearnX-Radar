"""Propose new config.SKILL_ALIASES entries by finding near-duplicate skill names.

Embeddings can rank which skill names are close, but they cannot tell "same skill,
new name" from "different but related skill" — a 2026-06-20 sweep found NIM rates
PostgreSQL~SQLite and machine learning~deep learning as close as real variants. So
this is a SUGGESTION tool, not an auto-merger: it prints the closest UN-aliased
pairs as copy-paste-ready alias lines for a human to accept or reject. The live
scorer stays on exact name + the curated alias map (config.MOMENTUM_SEMANTIC_MATCH
is off); approving good pairs here is what actually fixes the momentum signal.

It only surfaces pairs not already collapsed by SKILL_ALIASES, so re-running after
you accept some shows only what's still open — run it weekly, accept the obvious
variants, ignore the rest. Direction is suggested less-frequent -> more-frequent
(the established name becomes canonical); flip any line if you disagree.

Pure/offline by default (lexical embedder). Pass --nim for NVIDIA NIM embeddings
(needs NVIDIA_API_KEY; better at ranking true synonyms). Backend sets the default
threshold (NIM cosines run higher); override with --threshold.

Run from repo root:  python -m scripts.exp_semantic_match [--nim] [--threshold X]
Deletable — not part of the cron pipeline.
"""
import sys

import config
from radar.semantic_match import cosine, lexical_embedder, nim_embedder
from radar.skill_extractor import _canonical
from storage import load_trending_history

_BATCH = 32  # names per embedder call (keeps NIM request sizes modest)


def _vocabulary() -> tuple[list[str], dict[str, int]]:
    """Distinct canonical skill names + how many days each appeared (its weight)."""
    history = load_trending_history()
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


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    use_nim = "--nim" in sys.argv
    threshold = 0.80 if use_nim else 0.60  # NIM cosines sit higher than lexical
    if "--threshold" in sys.argv:
        threshold = float(sys.argv[sys.argv.index("--threshold") + 1])

    embed = nim_embedder() if use_nim else lexical_embedder
    backend = "NVIDIA NIM embeddings" if use_nim else "offline lexical embedder"

    vocab, freq = _vocabulary()
    vectors: dict[str, object] = {}
    for i in range(0, len(vocab), _BATCH):
        chunk = vocab[i : i + _BATCH]
        for name, vec in zip(chunk, embed(chunk), strict=True):
            vectors[name] = vec

    print(f"vocabulary: {len(vocab)} distinct skill names")
    print(f"backend:    {backend}   threshold={threshold}\n")

    # All pairs above threshold. _canonical already applied SKILL_ALIASES, so any
    # pair the alias map already collapses shares a canonical and never appears.
    pairs: list[tuple[float, str, str]] = []
    for i in range(len(vocab)):
        for j in range(i + 1, len(vocab)):
            a, b = vocab[i], vocab[j]
            c = cosine(vectors[a], vectors[b])
            if c >= threshold:
                pairs.append((c, a, b))
    pairs.sort(reverse=True)

    if not pairs:
        print("No un-aliased pairs above threshold — nothing to review.")
        return

    print(f"{len(pairs)} candidate pair(s) — accept the real variants, reject "
          "related-but-distinct ones (e.g. postgresql/sqlite):\n")
    print("  # cosine  suggested SKILL_ALIASES line (variant -> canonical)")
    for c, a, b in pairs:
        # Map the less-seen name onto the more-established one.
        variant, canon = (a, b) if freq[a] <= freq[b] else (b, a)
        print(f'  # {c:.3f}  "{variant}": "{canon}",   '
              f"(seen {freq[variant]}d vs {freq[canon]}d)")
    print(f"\nPaste the accepted lines into config.SKILL_ALIASES "
          f"(currently {len(config.SKILL_ALIASES)} entries). Re-run to confirm "
          "they no longer appear.")


if __name__ == "__main__":
    main()
