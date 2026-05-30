# v1 / Day 2 — Radar (skills → brief)

**Goal:** turn the ~200 scraped items into one markdown teaching brief for the
day's top skill gap. Three stages, called in order from `main.py`:

```
skill_extractor.extract(items)      -> list[Mention]      (1 LLM call)
gap_scorer.score(mentions, memory)  -> list[ScoredSkill]  (pure, no LLM)
gap_scorer.top(scored)              -> ScoredSkill | None
brief_writer.write(skill, memory)   -> markdown str        (1 LLM call)
```

Two LLM calls per run total — trivially inside the NVIDIA NIM free tier (40 RPM).
Scoring is pure Python (deterministic, offline-testable, no tokens).

---

## Shared shapes

```python
# Mention — emitted by skill_extractor (dedup'd across all items)
{
    "skill":    str,        # concrete, teachable: "DuckDB", "Server Components", ...
    "sources":  list[str],  # distinct source names that surfaced it
    "evidence": str,        # one line: why it showed up / what's notable
}

# ScoredSkill — gap_scorer enriches a Mention with:
{
    ...,                          # all Mention fields
    "score": float,
    "frequency": int,             # = len(set(sources)), kept for display
    "demand_weight": float,       # = sum of per-source weights (see below)
    "novelty": float,             # 1.0 unseen … decays with prior teaching
    "suggested_difficulty": str,  # beginner|intermediate|advanced
}
```

## Testability rule (LearnX-CLI pattern)

Each LLM-using function takes an injectable `chat_fn` defaulting to
`learnx.llm.chat`. Pure helpers (prompt build, JSON parse, scoring) are split
out so they unit-test offline with a canned response; only the real API call is
"live".

---

## 1. `skill_extractor.py`

- **Condense first (token hygiene):** build a compact digest — one line per item
  `[{source}] {title} :: {text[:200]}`. ~200 items × ~250 chars ≈ ~13K tokens,
  well inside GLM-5.1's 131K context, sent in **one** call.
- **Prompt** asks GLM-5.1 to extract concrete, teachable skills/tools/concepts
  (not company names, not job perks), and for each return `skill`, the distinct
  `sources` it appeared in, and a one-line `evidence`. Reply = JSON array only.
- **Parse** with `learnx.llm.parse_json_response`; one retry on parse failure
  (same belt-and-suspenders as LearnX-CLI's curriculum planner).
- **Guard:** drop mentions with empty `skill`; cap to top ~25 to keep scoring and
  the brief focused.
- `extract(items, chat_fn=chat) -> list[dict]`. Empty items → `[]`.

## 2. `gap_scorer.py` (pure)

**Source weighting (your call: favor real job-market demand over buzz).** Each
source carries a weight, defined in `config.SOURCE_WEIGHTS` so it's tunable
without touching code:

```python
SOURCE_WEIGHTS = {
    "HN Hiring":       2.0,   # real employer demand — strongest signal
    "Stack Overflow":  1.5,   # rising developer questions — real friction
    "GitHub Trending": 1.0,   # emerging tools, but buzz-driven
    "dev.to":          0.5,   # community chatter — noisiest
}
DEFAULT_SOURCE_WEIGHT = 1.0   # any source not listed above
```

- `frequency = len(set(sources))` — kept for display/transparency.
- `demand_weight = sum(SOURCE_WEIGHTS.get(s, DEFAULT_SOURCE_WEIGHT)
  for s in set(sources))` — a skill in HN Hiring (2.0) outranks the same skill
  in two dev.to posts (0.5 each = 1.0). Cross-source corroboration still helps,
  but demand sources dominate.
- `novelty`: look up `memory["skills"][skill]`. Unseen → `1.0`. Seen → decays
  `1 / (times_taught + 1)` (taught once → 0.5, twice → 0.33 …) so we stop
  re-teaching the same thing. (Full v2 spaced-repetition deepens this later.)
- **`score = demand_weight * novelty`.**
- `suggested_difficulty` from prior exposure: `times_taught` 0 → beginner,
  1 → intermediate, ≥2 → advanced. (Auto-scaling is a v2 goal; this is the cheap
  seed of it — default stays beginner when memory is empty.)
- `score(mentions, memory)` returns the list ranked high→low. `top()` already
  exists (returns `[0]` or None).

Ties (same score) break by `frequency` then `skill` name, so ranking is
deterministic — important for the offline unit tests.

## 3. `brief_writer.py`

- **One LLM call** producing a markdown teaching brief for the top skill — the
  document handed to the learnx curriculum stage (Day 3).
- **Structure** (target ~500–700 words):
  ```
  # {skill}
  ## Why it's on the radar today
  (uses evidence + which sources surfaced it)
  ## What you'll learn
  (3–5 concrete concepts to cover)
  ## Core ideas
  (the actual teaching content, prose + short examples)
  ## Where it fits
  (how it connects to the broader stack)
  ```
- **v2 hook (not built now):** when `memory` holds prior lessons, prepend a
  "connects to what you learned" line. For v1 memory is empty, so the prompt
  conditionally includes that only if prior skills exist.
- `write(skill, memory, chat_fn=chat) -> str`.

## Prompts

Live as text files in `radar/prompts/` (`extract.txt`, `brief.txt`), loaded with
a small `_load_prompt` helper — mirrors LearnX-CLI's `prompts/` convention and
keeps prompt wording out of the Python.

---

## Testing

- **Offline unit tests** (`radar/tests/`):
  - `gap_scorer`: synthetic mentions + memory → assert source weighting (an
    "HN Hiring" skill outranks a "dev.to"-only skill of equal raw frequency),
    novelty decay, difficulty scaling, tie-breaking, empty-input handling.
    (Pure, deterministic.)
  - `skill_extractor._parse`/digest + `brief_writer` prompt build: feed a canned
    `chat_fn` returning fixed JSON/markdown → assert shapes, no network.
- **Live integration (manual):** run `extract → score → brief` over the real 202
  items with the configured key; eyeball that the top skill is sensible and the
  brief reads like teachable material. Save a sample brief to `output/` for the
  Day 3 curriculum work to consume.

## Emerging-vs-popular fix (added after first live run)

First live run picked **"Python"** as the top skill — ubiquitous, not a gap.
With empty memory every novelty is 1.0, so broad terms hitting all four sources
dominate. Two-part fix (both, per sign-off):

1. **Extraction prompt** now tells the model to favor emerging/specific skills
   and to NOT return broad languages/ecosystems on their own (a specific
   technique within one is fine, e.g. "Python asyncio").
2. **Scorer stoplist** — `config.TABLE_STAKES_SKILLS` (tunable) multiplies a
   listed skill's score by `config.TABLE_STAKES_PENALTY` (0.1). Match is exact +
   normalized, so "Python" sinks but "Python asyncio" doesn't. Adds
   `table_stakes: bool` to ScoredSkill for transparency. Deterministic backstop
   to the prompt's softer guidance.

## Acceptance criteria — DONE (2026-05-30)

- [x] Radar runs scrape → extract → score → brief without error and prints the
      chosen skill + score (validated via a standalone live runner; `main.py`
      wiring unchanged, still halts at the learnx stub for Day 3).
- [x] Exactly two LLM calls per run (extract + brief; scoring is pure).
- [x] gap_scorer + extractor + brief_writer unit tests pass offline (21 total),
      incl. weighting, novelty, difficulty, tie-break, truncation salvage, and
      table-stakes penalty.
- [x] A real brief is generated from live data, saved to `output/sample-brief.md`.

**Resolved during build:** extraction truncated at 2000 tokens (raised to 4000 +
added `_salvage` to recover whole objects from a cut-off array, so a long
generation never kills the cron); emerging-vs-popular bias (above); the LLM
client had no timeout (SDK default 600s × 3 retries → ~30 min hang) — added a
120s timeout + `max_retries=0`; and the plan's `z-ai/glm-5.1` proved unreliable
on the NIM free tier (10-token call timed out at 90s) so the canonical model is
now `meta/llama-3.3-70b-instruct` (full run: ~54s, vs hanging before).

## Out of scope (later)

- Audio generation (Day 3), delivery (Day 4).
- Full v2 spaced-repetition + prior-lesson references in the brief.
