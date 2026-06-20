# v10 / Day 37 — Backlog backpressure (stop generating when the learner falls behind)

**Goal:** the daily run generates a Dutch lesson every morning unconditionally. But
a lesson the learner never practices produces **no recall report** ([[day36-mistake-driven-dutch-coach]]
relies on those reports; v9 day 33 created them). Two things then go wrong as misses
pile up: (1) spaced repetition keeps advancing because *delivery* alone marks a word
"seen" (`record_dutch_lesson` bumps reps + pushes `due` out), so un-practiced words
silently drift to long intervals and stop appearing; (2) the learner returns to a
wall of stale, half-finished lessons. Close the gap: treat "no report = not finished,"
and after a few consecutive unfinished lessons **pause new generation** and nudge,
instead of burying the learner under new words. One saved result resumes the loop.

This is the inverse of the day 36 coach — that personalizes *what* is taught; this
decides *whether* to teach at all today. Same discipline: deterministic detection,
config-flagged, fully reversible, never touches the dev pipeline.

---

## 1. What counts as "unfinished" (deterministic, no LLM)

A delivered lesson is **finished** once a recall report exists for its date. The
report only lands when the learner practiced and saved at least one word — an
all-`x` ("not trained") report writes nothing (`record_dutch_recall` returns 0 and
logs no entry), so it correctly does **not** count as finished.

`dutch_unsubmitted_streak(memory)` counts, from the newest delivered lesson
backwards, the run of consecutive lessons with no report — the current backlog. It
stops at the first finished lesson, so finishing *any* recent day shrinks the streak
(matches "submit one day to resume"). Pure, unit-testable.

## 2. The pause (`main._build_dutch`)

Behind `DUTCH_BACKLOG_PAUSE_AFTER` (default 5; `0` disables): if the streak reaches
the threshold, `_build_dutch` returns a **nudge payload and no persist-state** before
any generation:

- **No new words, no audio, no trainer JSON, no SR advance.** Returning `None` for
  the state means `record_dutch_lesson` is skipped — critical, so a paused day isn't
  itself logged as another backlog item (the streak holds steady, not grows).
- **A short nudge rides the normal DM/email.** The delivery layer renders any Dutch
  payload that has `markdown`; an empty `quiz_words` means no quiz button, `mp3_path
  = None` means no attachment. The nudge points back to the trainer, where the
  unfinished lessons still live (`dutch_lesson.json` is the last one generated), so
  the learner already has everything needed to catch up — nothing is lost.

## 3. Resume

No new state is written while paused, so each morning re-evaluates the same backlog
and stays paused. When the learner finishes one day, the next run's `_ingest_inbound`
folds in that report; the streak drops below the threshold and generation resumes
automatically. No manual switch, no lost schedule.

## Config (`config.py`)

```python
DUTCH_BACKLOG_PAUSE_AFTER = 5   # consecutive unfinished lessons before pausing; 0 = never
```

## Testing (offline)

- streak: 5 delivered + 0 reports -> 5; finish the newest -> 0; a fresh unfinished
  lesson on top -> 1.
- streak stops at first finished: finishing an OLDER day still counts the unfinished
  run above it, not the whole history.
- empty memory -> 0 (cold start never pauses).
- Scope pytest to `storage` (+ `dutch`/`delivery` regression); ruff clean.

## Acceptance criteria

- [ ] After `DUTCH_BACKLOG_PAUSE_AFTER` consecutive unsubmitted lessons, no new
      lesson is generated — a nudge is delivered instead.
- [ ] A paused day advances no SR state and is not logged as a lesson.
- [ ] Saving one day's results resumes generation on the next run.
- [ ] `DUTCH_BACKLOG_PAUSE_AFTER = 0` = today's always-generate behavior.
- [ ] The dev (English) pipeline is untouched whether or not Dutch is paused.

## Out of scope

- **Re-delivering the pending lesson's audio** — the trainer link already reaches it;
  re-attaching the MP3 is a later nicety, not v1.
- **Review-only fallback before a hard pause** — could soften the cutoff (drop new
  words first, pause later); add only if the hard pause feels too abrupt in practice.
- **Counting partial completion** — one saved word finishes a lesson for now; a
  "finished = all words marked" rule is a refinement, not needed yet.