# v7 / Day 25 — Map-reduce extraction (accuracy)

**Goal:** fix how the radar *analyzes* the ~430 collected items. Today
[`skill_extractor.extract`](../../radar/skill_extractor.py) flattens every item
into one digest (~24k tokens) and makes **one** LLM call that must both (a)
discover skills and (b) tally, per skill, *which sources* mentioned it — capped at
~20–25 outputs ([config.MAX_SKILL_MENTIONS](../../config.py) = 25). Two accuracy
problems at Day-23 scale:

1. **Recall** — 430 items in, ≤25 skills out. The long tail of genuinely emerging
   skills is silently dropped because one pass decides what's "notable."
2. **Attribution** — the entire demand signal (`gap_scorer._demand_weight` sums
   `SOURCE_WEIGHTS` over the *distinct sources* per skill) rests on the LLM
   correctly tallying source tags across 24k tokens. A mis-tally silently skews
   the ranking, with no cross-check.

This is **Phase 2** of the retrieval roadmap (Phase 1 = brief grounding, done
Day 24; Phase 3 = vector DB for cross-day trends). It is **not** a retrieval/
vector-DB problem — the corpus fits in context. The fix is **map-reduce + making
source attribution deterministic** so the LLM stops doing arithmetic it's bad at.

---

## Core idea

Split the LLM's job in two and move the counting into Python:

```
MAP (recall):       chunk the corpus → extract candidate skills per chunk (LLM, K calls)
                    → union all candidates  (no global cap; recall, not selection)
REDUCE (merge):     canonicalize + merge variant names  (lexical + alias map [+ 1 LLM pass])
ATTRIBUTE (exact):  for each candidate, scan ALL items → the REAL set of sources
                    mentioning it + an evidence snippet   (deterministic, no LLM)
→ feed mentions to gap_scorer.score()  (unchanged — now fed accurate source sets)
```

The map step's only job becomes **discovery** (maximize recall). Attribution —
the part the demand weight depends on — becomes **exact** (a corpus scan), not an
LLM guess. `gap_scorer` and everything downstream are unchanged; they just receive
better-attributed mentions.

---

## Contract (unchanged)

`extract(items, chat_fn=chat) -> list[dict]`, each mention still
`{"skill": str, "sources": list[str], "evidence": str}`. Same signature and shape
[main.py:210](../../main.py) already calls — this slice changes the *internals*,
not the interface, so `gap_scorer`/dashboard/brief all flow through untouched.

---

## 1. MAP — chunked candidate extraction

- Chunk `items` into batches sized to a **token budget** (not a fixed item count —
  HN Hiring items are long, SO items tiny). Reuse `_build_digest` per chunk.
- Run the existing extract prompt per chunk (its per-call output cap is now a
  *per-chunk* cap, so total recall scales with chunk count, not a global 25).
- Each chunk failure-isolated (one bad chunk ≠ dead run); keep `_salvage` for
  truncated JSON.
- **Output:** the union of candidate skills across chunks (raw, possibly with
  near-duplicate names) — this is the recall surface.

> The map prompt can be trimmed to **discovery only** ("list teachable skills";
> drop the "list the sources" instruction) since attribution is now deterministic.
> Keeps each call cheaper and removes the LLM-tally failure mode at the source.

## 2. REDUCE — canonicalize + merge variants

Merge `k8s`/`Kubernetes`, `React Server Components`/`RSC`, casing/punctuation
variants, so they don't split the demand signal across rows.

- **Always:** lexical normalize (lowercase, strip, collapse whitespace/punct) +
  a small curated **alias map** in config for the common ones (`k8s→kubernetes`,
  `rsc→react server components`, `postgres→postgresql`, …).
- **Optional (decision below):** one final LLM "merge these variant names" pass
  over the candidate list (cheap — names only, not the corpus).

## 3. ATTRIBUTE — deterministic source sets (the accuracy win)

For each canonical candidate, scan all `items`: a source *mentions* the skill when
the skill term appears in that item's `title`/`text`. Produce:
- `sources` = the distinct `source` values whose items matched (this is what
  `_demand_weight` sums — now exact, complete, and verifiable).
- `evidence` = a short snippet from the highest-signal matching item (replaces the
  LLM's 15-word guess; real text).

**Matching subtlety (must handle):** naive substring matching is wrong for short/
ambiguous names — "Go" matches "going", "C" matches everything, "R" is hopeless.
Mitigations:
- match on **word boundaries**, case-insensitive; multi-word skills matched as a
  phrase (these are the precise, high-value ones anyway);
- the existing `TABLE_STAKES_SKILLS` stoplist already sinks the most ubiquitous
  bare-language terms in scoring, so a few false matches there are harmless;
- for a short candidate (≤2 chars, or in a small ambiguous-token denylist) where
  boundary matching is still unreliable, **fall back** to the map step's
  LLM-reported sources rather than the corpus scan.
This subtlety is the main correctness risk and gets dedicated tests.

---

## Config additions (`config.py`)

```python
# --- Map-reduce extraction (v7 Day 25) ---
EXTRACTION_MAPREDUCE = True       # False -> legacy single-pass extract (rollback switch)
EXTRACTION_CHUNK_TOKENS = 6000    # token budget per map chunk — PROVISIONAL, see experiment
EXTRACTION_MAX_CANDIDATES = 60    # safety cap on merged candidates before attribution
SKILL_ALIASES = {                 # variant -> canonical, applied in REDUCE
    "k8s": "kubernetes", "rsc": "react server components", "postgres": "postgresql",
    # extend as variants are observed
}
AMBIGUOUS_SHORT_SKILLS = {"go", "c", "r", "d"}  # corpus-scan unreliable -> use LLM sources
```

`MAX_SKILL_MENTIONS` stays as the **post-scoring** keep (gap_scorer still trims to
the top 25 for the brief/dashboard) — map-reduce lifts only the *extraction* cap,
so recall rises without flooding downstream.

---

## Experiment: chunk size + recall/accuracy vs cost

Per project principle, the tunables are measured, not guessed (see
[[experiment-tunable-params]]). Extend `scripts/exp_grounding.py`'s pattern with
`scripts/exp_extraction.py` (deletable) over a saved `output/source_test_*.json`:

- **Sweep** `EXTRACTION_CHUNK_TOKENS ∈ {4k, 6k, 8k, 12k, ∞}` (∞ = today's single
  pass = baseline).
- **Measure:** total candidates discovered (recall proxy), LLM calls + wall-clock
  (cost), and — the real point — **attribution accuracy**: for a sample of skills,
  does the deterministic source set match a hand-checked truth better than the
  single-pass LLM tally? Plus how many distinct sources each method finds.
- **Decision rule:** largest chunk budget (fewest LLM calls) still at near-max
  recall — the knee. Smaller spends extra calls on candidates already found (or
  long-tail noise filling the cap); larger drops real skills.

### Result (run 2026-06-05, corpus = output/source_test_2026-06-05.json, 429 items)

| chunk budget | chunks/LLM calls | candidates (recall) | avg sources/skill |
|---|---|---|---|
| 4k | 7 | 60 (cap) | 1.65 |
| **6k** | **5** | **60 (cap)** | 1.73 |
| 8k | 4 | 45 | 1.87 |
| 12k | 3 | 43 | 1.56 |
| ∞ (single pass) | 1 | 18 | 1.61 |

**Chosen: `EXTRACTION_CHUNK_TOKENS = 6000`.** 6k ties 4k at the recall cap (60)
with fewer LLM calls (5 vs 7); 8k drops to 45 (a real, sub-cap fall), so 6k is the
largest budget still at max recall — the knee. The headline: map-reduce@6k finds
**60 candidates vs the single pass's 18** (~3.3× recall), which was the whole point.

> **Notes:** (1) `avg sources/skill` stays ~1.6–1.9 across all budgets —
> confirming attribution is chunk-independent (deterministic scan), so chunk size
> trades *only* recall vs cost, as designed. (2) Wall-clock was dominated by an
> anomalously slow NIM day (~90s/call; 0 failures), so it's not a fair signal —
> on a normal day (~6s/call) 6k's 5 calls ≈ 30s, well inside the cron budget; the
> decision rests on recall vs call-count, not that day's latency. (3) 4k/6k are
> censored at `EXTRACTION_MAX_CANDIDATES=60`; downstream `MAX_SKILL_MENTIONS=25`
> trims after scoring, so 60 is ample headroom and the cap needn't rise.

---

## Testing

Offline (canned `chat_fn`, fixture corpus):

- **map:** N chunks → union recall exceeds a single capped pass on the same input.
- **reduce:** `k8s` + `Kubernetes` + `kubernetes` collapse to one; alias map +
  lexical normalize both exercised.
- **attribute:** a skill mentioned in HN + dev.to items yields exactly
  `{"HN ...", "dev.to"}`; word-boundary matching rejects "go" inside "going";
  a short ambiguous skill falls back to LLM-reported sources.
- **contract/rollback:** output still satisfies the 3-key mention contract;
  `EXTRACTION_MAPREDUCE=False` reproduces the legacy single-pass result.
- Scope pytest to Radar pkg dirs (+ `research`); `ruff` clean.

## Acceptance criteria

- [x] On a real corpus, map-reduce discovers materially more candidate skills than
      the single pass (60 vs 18 at 6k); attribution is a deterministic corpus scan
      with explicit tests asserting real source sets over the LLM's tally.
- [x] `gap_scorer`, brief, dashboard, delivery unchanged and still pass (139 tests).
- [x] `EXTRACTION_MAPREDUCE=False` is a clean one-switch rollback (tested).
- [x] Chunk size set from the experiment (6k), not guessed; table + rationale recorded.
- [x] Offline tests pass; `ruff` clean.

## Out of scope

- **Phase 3 — vector DB** (cross-day semantic trend tracking + semantic dedup).
  Reduce-step variant merging here is *within a single day* and lexical/alias-based;
  semantic, cross-day merging is the vector-store job. See
  [[learnx-radar-retrieval-roadmap]].
- Embedding-based clustering for the reduce step (a heavier alternative to the
  alias-map merge) — revisit only if lexical+alias merging proves too coarse.
- Changing `gap_scorer` weights/formula — untouched here.
