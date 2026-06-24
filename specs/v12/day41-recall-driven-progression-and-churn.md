# v12 / Day 41 — Act on the signal: recall-driven CEFR progression, a contrast tool for stuck words, an honest streak, and the radar case-churn fix

**Goal:** the engine *measures* learning well but largely *ignores its own
measurements*. A read of the live state ([state repo](https://github.com/Yusuprozimemet/LearnX-Radar-state),
through 2026-06-24) made four gaps concrete:

- The owner held **86% recall (61/71)** across 10 reports for two weeks, yet
  `cefr` never left **A2** — mastery is measured and discarded
  ([[day36-mistake-driven-dutch-coach]] explicitly deferred progression).
- `email` was recalled **wrong ×3, right ×0** and `gebruiker` **wrong ×2** — both
  force-reviewed in nearly every recent lesson, both still failing. Re-exposure has
  a ceiling on *confusable* words; the coach's one tool ("show it again") can't fix
  them.
- `streak` read **2** while the learner reported ~10 of the last 14 days. The metric
  counted consecutive **cron** days (≈"did the job run"), which a same-day re-run
  resets to 1 — it measured the machine, not the learner.
- `langchain` was recorded under **three case-variant keys** (`Langchain` ×2,
  `LangChain` ×2, `langchain` ×1) → **5 lessons in 18 days**. `skill_memory` is
  keyed by the display surface form, so the spaced-repetition novelty signal
  (`gap_scorer._novelty`) read the case-variant as never-taught and re-taught it.

Each fix closes the gap between *what we record* and *what the engine does next*.
None touches the frozen-vocabulary or zero-backend disciplines.

---

## 1. Recall-driven CEFR progression (`dutch/progress.py`, `main.py`)

Day 36 deferred A2→B1 advancement as "higher-stakes." The data says it's the single
highest-value lever: the goal is the inburgering **B1**, and the learner is parked at
A2 despite clearing it. The frozen bank is A2 vocab — so progression raises the
**sentence/grammar complexity the lesson prompt asks for**, not the words. The LLM
already takes `{cefr}` in [dutch/prompts/lesson.txt](../../dutch/prompts/lesson.txt);
advancing the level is enough to make the wrapping harder.

`advance_cefr(memory, today) -> (cefr, advanced)` — pure, deterministic, mutates
`memory["cefr"]`/`memory["cefr_since"]` only on an advance. Conservative, one rung at
a time along `DUTCH_CEFR_LADDER = ("A2", "A2+", "B1")` (capped at the goal):

- Only recall reports dated on/after `cefr_since` and within
  `DUTCH_CEFR_ADVANCE_WINDOW_DAYS` count, so cleared progress doesn't carry into the
  next rung (each rung earns its own promotion).
- Needs **both** enough reports (`DUTCH_CEFR_ADVANCE_MIN_REPORTS = 6`) and enough
  attempted words (`DUTCH_CEFR_ADVANCE_MIN_WORDS = 30`) before the rate is trusted —
  a couple of lucky days can't promote — and pooled `right/total ≥
  DUTCH_CEFR_ADVANCE_RECALL = 0.85`.

Thresholds are deliberately conservative (the owner sat at ~86%) and are plain config
knobs, tunable as data accrues. Wiring: `main._build_dutch` calls it on the loaded
memory before selection (single-user), so the bumped level flows into `build()` and is
persisted with the SR state; `_persist_dutch_multiuser` advances each learner on their
**own** recall (generation stays global — only the per-user scorecard level changes).

## 2. A contrast tool for stuck words (`dutch/coach.py`, `dutch/lesson.py`)

The coach gains a **second tool**, deterministic and LLM-free (like the cloze). A word
is **stuck** when `recall_wrong ≥ DUTCH_COACH_STUCK_MISSES` (2) **with zero** successful
recalls — re-exposure provably isn't working, so it's confused with a neighbour, not
unlearned. The neighbour is chosen from the learner's **own** data: the word most often
in the same report's `wrong` list (`email` and `gebruiker` co-failed twice).

- `confusable_pairs(memory, bank)` → `[{id, nl, en, with_id, with_nl, with_en}]`, both
  words from the frozen bank, capped at `DUTCH_COACH_MAX_CONTRAST` (2). A stuck word
  that never co-failed yields no pair (nothing to contrast).
- `render_contrast(pairs)` → a gloss-only **"Let op het verschil"** markdown section
  (nothing invented — words and meanings come from the bank).
- `lesson.build` gains `extra_sections: str = ""`, inserted between the cloze and the
  trainer link; `main` force-reviews **both** words of each pair (prepended to
  `force_review_ids` ahead of the coach's focus words) so the disambiguation lands.

This is the day-36 "select/emphasize within the frozen bank, never invent" rule
extended with a confusion signal — the same correct-by-design posture.

## 3. An honest streak = adherence, not cron uptime (`storage/state.py`)

`dutch_recall_adherence(memory, today, window_days=DUTCH_STREAK_WINDOW_DAYS=30)` —
the count of **distinct recall-report lesson-dates** in the trailing window:
*how many recent lessons the learner actually finished*. `record_dutch_lesson` sets
`memory["streak"]` from it instead of the consecutive-cron count. Robust to batched
reports (many submitted on one day) and to same-day re-runs.

## 4. Radar case-churn fix (`storage/state.py`, `radar/gap_scorer.py`)

`_canonical` already lowercases, so **scoring and momentum** collapse case variants —
the churn lives downstream, where `skill_memory` is keyed by the display surface form:

- `skill_entry(memory, skill)` resolves an entry **case-insensitively** (the existing
  key under whatever case it was first stored). `_novelty` uses it, so a case-variant
  surface no longer reads as never-taught and resets suppression.
- `record_lesson` reuses an existing case-variant key (`_existing_skill_key`) instead
  of forking a new one — future lessons append to one entry.

Alias-equivalent variants (`autonomous agents` → `autonomous ai agents`) are already
merged upstream into one display name, so only case/whitespace differs between days —
exactly what the fold catches. (The three historical `langchain` keys are not
retro-merged; the fix kills *future* churn. A one-time consolidation is optional.)

## Config (`config.py`)

```python
# Recall-driven CEFR progression
DUTCH_CEFR_PROGRESSION        = True
DUTCH_CEFR_LADDER             = ("A2", "A2+", "B1")
DUTCH_CEFR_ADVANCE_RECALL     = 0.85
DUTCH_CEFR_ADVANCE_MIN_REPORTS = 6
DUTCH_CEFR_ADVANCE_MIN_WORDS  = 30
DUTCH_CEFR_ADVANCE_WINDOW_DAYS = 30
# Coach's contrast tool for stuck words
DUTCH_COACH_STUCK_MISSES = 2   # wrong this many times with ZERO recalls -> "stuck"
DUTCH_COACH_MAX_CONTRAST = 2   # cap on contrast pairs per lesson
# Adherence streak
DUTCH_STREAK_WINDOW_DAYS = 30
```

`dutch_memory` gains `cefr_since` (when the current rung began; backfilled to the
default shape).

## Testing (offline, pure functions)

- **progression:** promotes at 100%/6 reports/30 words; holds at 50%; holds with too
  few reports; caps at B1; ignores reports earned before `cefr_since`.
- **contrast:** pairs a stuck word with its top co-failed neighbour; excludes words
  ever recalled right; skips a stuck word with no co-failure; `render_contrast` is
  gloss-only and empty without pairs.
- **streak:** `dutch_recall_adherence` counts distinct in-window dates (batched same-day
  counts once; older-than-window excluded); `record_dutch_lesson` sets streak from it.
- **case-fold:** novelty suppresses a `langchain` surface against a `LangChain` entry;
  `record_lesson` keeps one key across case variants; `skill_entry` matches
  case-insensitively.
- Full suite + ruff green (264 tests at time of writing). Validated against the live
  state: owner advances **A2→A2+**, streak **2→10**, pair **email↔gebruiker**,
  `langchain` resolves to the existing entry.

## Acceptance criteria

- [ ] Sustained high recall at a rung advances the learner one level toward B1; low or
      thin data holds; B1 is the ceiling.
- [ ] A word wrong repeatedly with no recalls triggers a gloss-only contrast section and
      both words are force-reviewed.
- [ ] `streak` reflects lessons completed in the window, unaffected by re-runs/batching.
- [ ] A skill recorded under one case is not re-taught under another; no new split keys.
- [ ] Every feature is behind a config flag; all degrade gracefully and never block the
      lesson or the dev pipeline.

## Out of scope (still parked)

- **Production track (Spreken/Schrijven), KNM, mock exams** — the next exam-coverage
  slices ([[dutch-production-parked]]); progression makes them more valuable but is
  independent.
- **Rating capture for the dev track** — the loop is correctly wired but needs
  `TELEGRAM_BOT_USERNAME` set + taps; it's operational, not code. Once data accrues it
  decides whether the radar track earns continued investment.
- **One-time consolidation** of the existing three `langchain` keys — cosmetic.
- **Experiment-swept thresholds** — the progression constants are conservative
  defaults; sweep them like the momentum window ([[day26-momentum-and-vectordb]]) once
  enough multi-rung history exists.