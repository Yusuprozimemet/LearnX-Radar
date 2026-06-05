# v6 / Day 19 — Adaptive pacing + growing the B1 word bank

**Goal:** the two enabling changes that turn the v5 A2 coach into a B1 path: (1) the
daily new-word count becomes **adaptive** (gentle → faster as the learner sustains a
streak and high review accuracy), with a CEFR auto-advance A2→B1; (2) the curated
word bank grows toward the **B1 range (~2,500–3,200 words)** via reviewed batches.
Both refine v5 day-17 rather than replacing it; the "frozen, human-reviewed Dutch
data" guardrail is untouched.

---

## Part A — Adaptive pacing

Today `DUTCH_NEW_WORDS_PER_DAY` is a constant. Replace its *use* (not the constant —
keep it as the floor) with a small pure function of the learner's state in
`dutch_memory.json`.

### Config (`config.py`)

```python
DUTCH_NEW_WORDS_MIN = 5          # floor (was DUTCH_NEW_WORDS_PER_DAY)
DUTCH_NEW_WORDS_MAX = 12         # ceiling
DUTCH_PACE_STREAK_STEP = 7       # +1 new word per this many days of streak
DUTCH_PACE_MIN_ACCURACY = 0.7    # below this recent review accuracy, hold at the floor
DUTCH_CEFR_ADVANCE_WORDS = 1800  # introduced-word count that flips A2 -> B1
```

### `dutch/pacing.py`

```python
def words_today(memory: dict) -> int:
    """Adaptive new-word count for today, clamped to [MIN, MAX].
    Grows with streak (streak // STREAK_STEP), but is held at MIN when recent review
    accuracy < MIN_ACCURACY (don't pile on new words while old ones aren't sticking)."""

def cefr_for(memory: dict) -> str:
    """'A2' until introduced-word count reaches DUTCH_CEFR_ADVANCE_WORDS, then 'B1'.
    Monotonic — never downgrades. Written into memory['cefr'] on each run."""
```

**Review accuracy** needs a signal. The self-directed Perplexity quiz can't report
back (no inbound channel — the project's standing constraint), so accuracy is a
*proxy*: the fraction of due words the learner has kept up with — i.e. words reviewed
on/before their due date vs. overdue. `record_dutch_lesson` already knows which due
words were served; track a rolling `reviews_on_time` / `reviews_due` count in memory
and derive accuracy from it. (A real graded signal is a v7 concern with writing/mock
exams; documented as the future upgrade.)

`dutch/wordlist.select_for_today` and `main.py` call `pacing.words_today(memory)`
instead of reading the constant; `cefr_for` updates `memory['cefr']` each run, which
the dashboard already displays.

---

## Part B — Growing the word bank to B1

`dutch/build_wordlist.py` (introduced in day 16 as the one-time generator) is the
tool; day 19 is about *using it at scale* and keeping quality.

- **Batch by CEFR + theme + word-class**: generate A2 then B1 tiers, tagged
  `cefr: "A2" | "B1"`, across more themes (health, housing, education, money,
  travel, feelings, work, plus the tech set). The selector prefers the learner's
  current CEFR tier and below, so B1 words don't surface before A2 is consolidated.
- **Dedup on merge** by `id`; never drop or rewrite an existing reviewed entry
  (append-only growth keeps the committed file stable and review effort incremental).
- **Review gate**: each generated batch is human-skimmed for `de`/`het`, spelling,
  and level before it's merged and committed. The daily pipeline still never calls
  the generator.

### Selector change (`dutch/wordlist.py`)

`select_for_today` gains a `cefr` arg (from `pacing.cefr_for`): new words are drawn
from entries whose `cefr` is at or below the current level, in list order. Everything
else (due-review logic, theme alternation) is unchanged from day 17.

---

## Testing (offline)

- `pacing.words_today`: returns MIN at streak 0; increases one step per
  `PACE_STREAK_STEP` days; clamps at MAX; drops to MIN when proxy accuracy < threshold.
- `pacing.cefr_for`: 'A2' below the threshold, 'B1' at/above; never downgrades.
- `select_for_today` with `cefr='A2'`: excludes B1-tagged words; with `cefr='B1'`:
  includes both tiers.
- Bank integrity test: `wordlist.json` loads, ids unique, every entry has
  `cefr in {A2,B1}` and (for nouns) an article — a CI guard against a bad batch merge.

## Acceptance criteria

- [ ] New-word pace adapts to streak + a review-accuracy proxy, within [MIN, MAX].
- [ ] CEFR auto-advances A2→B1 by introduced-word count and is shown on the dashboard.
- [ ] The word bank can grow in reviewed, append-only B1 batches; the selector
      respects the learner's current tier.
- [ ] Offline tests pass; ruff clean; no change to committed pipeline state files.

## Out of scope

- A graded (true) accuracy signal — needs an inbound/answer-checking channel (v7).
- B1→B2 progression; the exam target is B1.
