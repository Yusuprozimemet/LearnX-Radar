# v2 / Days 5–6 — Adaptive learning (spaced repetition + difficulty flow)

**Goal:** lessons stop feeling like random daily trivia and start feeling like a
curriculum — the radar revisits topics on a spaced schedule, lessons deepen on
re-encounter, and briefs bridge to related prior lessons.

Builds on v1's already-seeded memory mechanics (`skill_memory.json` with
`times_taught` / `last_taught` / `lessons`, novelty weighting, difficulty calc).

---

## Day 5 — Spaced-repetition scoring (`gap_scorer` + `config`)

Replace the time-blind `novelty = 1/(times_taught+1)` with a **time-aware** model
that uses the `last_taught` date already stored:

- **Unseen skill** → novelty `1.0` (max — the core gap signal).
- **Taught skill** → it's suppressed right after teaching and becomes eligible
  again only after a spacing interval that grows with each repetition:
  ```
  interval_days = SR_BASE_INTERVAL_DAYS * SR_SPACING_FACTOR ** (times_taught - 1)
  novelty       = clamp(days_since_last_taught / interval_days, 0.0, 1.0)
  ```
  So a skill taught today → ~0 novelty (won't be re-picked); after `interval`
  days it climbs back to 1.0 and resurfaces — now at a higher difficulty.
- Spacing widens per repetition: with base 7, factor 2 → 7d, 14d, 28d…
- Edge cases: entry with no `last_taught` → treat as due (1.0); `times_taught` 0
  → unseen path.

`config`: `SR_BASE_INTERVAL_DAYS = 7`, `SR_SPACING_FACTOR = 2.0`.
`score` keeps `demand_weight × novelty × table_stakes_penalty`; difficulty
scaling (`beginner→intermediate→advanced` by `times_taught`) is unchanged.

## Day 6 — Adaptive briefs + difficulty flow

**(a) Difficulty actually changes the lesson.** Today difficulty is computed and
recorded but ignored by generation. Thread it into the curriculum planner:

- `learnx.constants.DIFFICULTY_CONTEXT` — a dict of guidance per level (beginner:
  define terms, lead with intuition, max complexity 2; intermediate: assume
  basics, go into mechanics/tradeoffs/pitfalls; advanced: edge cases, perf,
  production gotchas, concise).
- `curriculum.plan(brief_md, title, duration_min, difficulty="beginner", chat_fn)`
  injects `{difficulty}` + `{difficulty_context}` into `curriculum.txt`.
- `main.py` passes `skill["suggested_difficulty"]` into `curriculum.plan`.

**(b) Briefs bridge to a related prior lesson.** Today `_prior_context` lists the
last 3 skill *names* generically. Make it deliberate:

- Store a one-line `summary` per lesson in memory so the bridge has substance.
  `record_lesson(..., summary=...)`; `main.py` passes `lesson["summary"]`.
- `brief_writer._prior_context(memory, current_skill)` lists recent lessons as
  `skill — summary` and instructs: *if one is genuinely related to
  `current_skill`, open with a one-sentence bridge; otherwise don't force it.*

---

## Testing (offline)

- **gap_scorer spaced-repetition** (`radar/tests`): synthetic memory with dated
  `last_taught` → assert just-taught ≈ 0 novelty (drops in ranking), taught past
  its interval ≈ 1.0 (resurfaces), unseen = 1.0, interval widens with
  `times_taught`, missing-date → due.
- **curriculum difficulty injection** (`learnx/tests`): canned `chat_fn` captures
  the prompt → assert the chosen difficulty's context text is present.
- **brief bridge** (`radar/tests`): memory with a related prior lesson → captured
  prompt contains that skill + summary and the bridge instruction; empty memory →
  no prior-context block.
- **storage**: `record_lesson` stores `summary`.

## Acceptance criteria — DONE (2026-05-30)

- [x] A skill taught today scores 0 (novelty 0) and won't be re-picked; after its
      interval it returns to novelty 1.0 at the next difficulty. Intervals widen
      per repetition (7 → 14 → 28 d). Proven in `radar/tests/test_radar.py`.
- [x] `curriculum.plan(... difficulty=...)` injects the level's `DIFFICULTY_CONTEXT`
      into the prompt — verified via captured prompt in `learnx/tests`.
- [x] `brief_writer._prior_context(memory, skill)` lists prior lessons as
      `skill — summary` and instructs a bridge only if genuinely related; empty
      memory → no block. `record_lesson` now stores `summary`.
- [x] All offline tests pass — 36 total (4 net new for v2).

**Note:** the adaptive loop (a skill getting suppressed/deepened across days) is
proven by deterministic unit tests with seeded `last_taught` dates. Seeing it
live requires two seeded runs; not run to save tokens/time.

## Out of scope

- `/recap` Telegram Q&A bot (deferred — different architecture).
- v3 dashboard.
