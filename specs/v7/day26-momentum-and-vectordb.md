# v7 / Day 26 — Cross-day momentum (Phase 3)

**Goal:** make the radar reward skills that are *genuinely rising over time*, not
one-day spikes — and recognize the same rising skill across days even when its
name varies. This is **Phase 3** of the retrieval roadmap
([[learnx-radar-retrieval-roadmap]]): Phase 1 grounded the brief, Phase 2 fixed
extraction recall + attribution *within a day*; Phase 3 adds the **time axis**.

Today the only temporal signals are spaced-repetition novelty (about *what we've
taught*, not *what the world wants*) and Stack Overflow week-over-week counts (one
source). A skill that trends hard for one day and vanishes is scored the same as
one climbing for two weeks. Momentum fixes that.

---

## The honest framing (read this before the vector DB)

The roadmap called Phase 3 "the vector DB." But a vector store is an
*implementation detail*, not the goal — and we already hold most of what we need:
`trending_history.json` keeps a **per-day ranking** (`{date: {today_skill,
scored:[...]}}`), and Phase 2 gives every skill a **canonical name**
(`skill_extractor._canonical`, alias-aware). So cross-day linking is mostly a
*lookup by canonical name across days* — **no embeddings required**.

Embeddings only add value for the residual: semantic variants the alias map
doesn't catch (`"RSC"` ↔ `"React Server Components"`, `"LLM agents"` ↔ `"agentic
AI"`). That's real but secondary. Consistent with how we've worked (don't build
infra ahead of the problem), this slice is split:

- **Phase 3a — momentum signal (no vector DB).** Compute rising/recurring from
  `trending_history` + canonical names; feed it into `gap_scorer`. Cheap, fully
  testable, probably ~90% of the value.
- **Phase 3b — semantic cross-day linking (vector DB), ESCALATION.** Only if 3a's
  canonical matching measurably misses cross-day variants. Embedded store +
  NIM embeddings. Specced here but gated on evidence from 3a.

**Recommendation: build 3a first, measure how many cross-day links canonical
matching misses, then decide on 3b.**

---

## Phase 3a — momentum signal

### Data

`trending_history.json` already records each day's `scored` (skill, sources,
demand_weight, score). Two changes:
- **Persist the canonical name** alongside each scored skill (so cross-day lookup
  is exact, alias-aware) — add `canonical` in `gap_scorer.score` output (cheap;
  reuses `skill_extractor._canonical`).
- **Raise the history cap** if needed: `HISTORY_KEEP_DAYS` must cover the momentum
  window (below). Check current value; widen if short.

### The signal

For each of today's scored skills, look back over the last `MOMENTUM_WINDOW_DAYS`
of history (matched by canonical name) and compute:
- **recurrence** — how many of the last N days the skill appeared (sustained
  interest vs one-off).
- **trend** — slope/delta of its `demand_weight` (or distinct-source count) across
  the window (accelerating vs fading).

Combine into a **momentum multiplier** and fold into the score, alongside the
existing factors (same pattern as `goal_boost`/`novelty`):

```
score = demand_weight × novelty × table_stakes × known × goal × MOMENTUM
```

- A skill rising across several days → boosted (catch it while it climbs).
- A one-day spike → neutral/slightly damped (don't over-react to noise).
- Orthogonal to novelty: momentum is "is the *world's* interest rising"; novelty
  is "have *we* taught it recently." Both apply.

### Config (`config.py`)

```python
# --- Cross-day momentum (v7 Day 26, Phase 3a) ---
MOMENTUM_ENABLED = True
MOMENTUM_WINDOW_DAYS = 14        # lookback window — PROVISIONAL, see experiment
MOMENTUM_MAX_BOOST = 1.5         # multiplier cap for a strongly-rising skill
MOMENTUM_SPIKE_DAMP = 0.9        # multiplier for a one-day spike (mild)
```

`MOMENTUM_ENABLED = False` reproduces exactly today's scoring (rollback).

### gap_scorer wiring

`score(mentions, memory, profile, history=None)` gains an optional `history`
(the loaded `trending_history`); when None or `MOMENTUM_ENABLED` is False, the
momentum multiplier is 1.0 and behavior is identical to v7-pre-momentum. `main.py`
passes `load_trending_history()` in. New helpers `_recurrence` / `_trend` /
`_momentum`, each unit-tested; emits a `momentum` field for the dashboard.

### Experiment (per principle — measure, don't guess)

`scripts/exp_momentum.py` (deletable) over the committed `trending_history.json`
(needs several days of real history — may require letting the cron accrue a week+
first, or backfilling from the per-day archive):
- **Sweep** `MOMENTUM_WINDOW_DAYS ∈ {7, 10, 14, 21}` and report, for recent days,
  how the top-skill pick changes vs no momentum, and whether boosted skills were
  genuinely sustained (manual check on a sample).
- **Decision rule:** smallest window that separates sustained risers from spikes
  without over-smoothing (a 21-day window may mute fast-but-real trends). Record
  the chosen window + rationale here and in config. **NB:** this experiment is only
  meaningful once enough history exists — gate it on accrued data.

### Result (partial, run 2026-06-05 — 6 days of history)

Ran `scripts/exp_momentum.py` on the 6 days accrued so far. The momentum *logic*
is validated on real data (LangChain, present all 5 prior days → max boost 1.5;
Agentic coding → 1.25; 12 skills boosted, 7 damped). **But the window sweep is
degenerate**: with <7 days of data, every window ∈ {7,10,14,21} sees the same
prior days, so all produce identical rankings. Window tuning is therefore
**deferred until ~14+ days of post-Phase-2 history accrue**; `MOMENTUM_WINDOW_DAYS`
stays at the provisional **14** until then. The feature ships gated and improving
with data; re-run the sweep in ~2 weeks to set the window from a non-degenerate
range.

---

## Phase 3b — semantic cross-day linking (vector DB) — ESCALATION, gated

Build **only if** 3a shows canonical matching misses too many cross-day variants
(measure: in 3a, log skill pairs that are obviously the same concept but didn't
match by canonical name; if that count is high, escalate).

### Design (when built)

- **Embedding model:** the existing NIM key exposes embedding endpoints (e.g.
  `nvidia/nv-embedqa-e5-v5` or `baai/bge-m3`) — keeps the single-provider design.
  Verify the exact model live once (project discipline).
- **Store (embedded, NOT hosted):** a hosted vector DB (Pinecone/Qdrant cloud)
  breaks the free / no-paid-API / Actions-cron / committed-state discipline.
  Options to decide between (scale is tiny — ~60 skills/day × ~365 = ~22k vectors):
  - `sqlite-vec` — single committable file, lightweight (leans best with the
    "state as committed JSON/file" pattern);
  - `LanceDB` — a directory of files, heavier;
  - `numpy` cosine over an `.npz`/JSON of vectors — no heavy dep, but git bloat.
- **Scope:** embed **skills** (cheap, ~60/day), not items — trend tracking needs
  skill-level vectors, not corpus dedup. Daily: embed today's canonical skills,
  upsert with date, and at lookup query the store for prior-day matches above a
  similarity threshold to extend `_recurrence`/`_trend` beyond exact-canonical.

### Decisions to flag for 3b (when we get there)

1. Store choice (sqlite-vec vs LanceDB vs numpy+npz) — vs the committed-state
   discipline and git size over a year.
2. Where the store lives: committed to the repo (like other state) vs a rolling
   GitHub Release asset (like the audio).
3. Similarity threshold — experiment-driven (precision/recall of cross-day links).

---

## Testing (3a)

Offline, fixture `trending_history`:
- recurrence: a skill present 6 of last 14 days scores higher recurrence than one
  present once.
- trend: rising `demand_weight` across the window boosts; falling damps.
- spike: a skill appearing only today gets the spike-damp, not a boost.
- canonical match: `k8s` today links to `Kubernetes` 3 days ago (alias-aware).
- rollback: `MOMENTUM_ENABLED=False` (or `history=None`) → identical to current
  scoring; existing gap_scorer tests unchanged.
- Scope pytest to Radar pkg dirs (+ `research`); `ruff` clean.

## Acceptance criteria (3a)

- [ ] A sustained-rising skill outranks an equal-demand one-day spike.
- [ ] `MOMENTUM_ENABLED=False` / no history = byte-identical to current scoring.
- [ ] `canonical` persisted in history; cross-day lookup is alias-aware.
- [ ] Window set from the experiment (once enough history), not guessed.
- [ ] Dashboard can show a momentum indicator; offline tests pass; ruff clean.

## Out of scope

- **Phase 3b vector DB** unless 3a proves canonical matching insufficient (gated
  above).
- Changing demand weights / novelty / table-stakes formulas — momentum is an
  additional multiplier only.
- Semantic dedup of the *item corpus* (vs skills) — different, larger effort.
