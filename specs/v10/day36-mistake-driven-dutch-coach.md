# v10 / Day 36 — Mistake-driven Dutch coach (personalize from your own recall)

**Goal:** today the Dutch lesson is selected mechanically — theme alternates by
the calendar (`wordlist.theme_for`), new words are "the first N never-introduced of
that theme," review words are "whatever's due." The Day 33 recall loop already
records *which words you get wrong* (`recall_wrong` / `recall_right` per word), but
that signal only adjusts spaced-repetition timing — it never changes **what gets
taught**. Close that gap: a small LLM coach reads your accrued recall history and
chooses today's **focus** — which struggling words to pull forward and what the
lesson should emphasize — so the lesson targets *your* weak spots, aimed at the
inburgering goal. This is the [[day26-momentum-and-vectordb]] pattern (an LLM makes
the judgment you'd otherwise make by hand, logged + overridable, running unattended)
applied to the Dutch track instead of the skill radar.

---

## 1. The honest framing (what's a real lever, what isn't)

The word bank (`dutch/wordlist.json`) is **frozen and human-reviewed** — the coach
must NOT invent vocabulary (that would bypass the curation discipline and risk
wrong/ungraded Dutch). So its levers are only over *selection and emphasis* of
existing curated words:

1. **Struggle-aware review** — pull words you keep failing into today's review set,
   even if spaced-repetition wouldn't list them as "due" yet.
2. **Focus directive** — a short instruction passed into the existing lesson prompt
   (`dutch/lesson.py`) so the example sentences emphasize the failing words and the
   pattern behind them (e.g. de/het gender, past tense), in an inburgering context.

Theme choice stays mechanical for now (low value to change; the bank only has two
themes). CEFR advancement is explicitly **out of scope** (Day 33 already flagged it
as separate and higher-stakes).

## 2. Detecting struggle (deterministic, no LLM)

From `dutch_memory["words"][id]`: a word is **struggling** when
`recall_wrong > recall_right` and `recall_wrong >= DUTCH_COACH_MIN_MISSES` (default
2 — one slip isn't a pattern). Rank by miss rate, then absolute misses. This is pure
and unit-testable; it produces the candidate set the coach reasons over. Words with
no recall data yet are not "struggling" (unknown ≠ failing) — so a brand-new learner
with no trainer history yields an empty set and the lesson falls back to today's
mechanical behavior (graceful cold start).

## 3. The coach call (`dutch/coach.py`, llama via NIM)

`plan(struggling, due_ids, memory, *, chat_fn=chat) -> dict`. Pure/injectable like
`alias_curator.curate`. Given the struggling words (with their counts and glosses)
it returns a small JSON plan:

```json
{ "focus_ids": ["bestand", "wachtwoord"],   // subset of struggling, capped
  "directive": "Emphasize de/het gender; these were missed as 'de' words.",
  "reason": "3 of the 4 misses this week were het-words taken as de." }
```

- **Conservative cap:** at most `DUTCH_COACH_MAX_FOCUS` (default 3) focus words, so a
  lesson is targeted, not a remediation dump. The asymmetry mirrors the curator:
  over-drilling discourages; under-drilling just costs a little, self-heals next run.
- `focus_ids` must be a subset of the struggling ids (others dropped — no
  hallucinated words); `directive` is free text fed to the lesson prompt.
- When `struggling` is empty (cold start / all-mastered) the coach is **skipped
  entirely** — no LLM call, today's selection unchanged.

## 4. Wiring (`dutch/wordlist.py` + `dutch/lesson.py` + `main.py`)

- `select_for_today` gains an optional `force_review_ids`: ids merged into the
  review set ahead of the cap, so coach focus words are guaranteed taught even if
  not strictly due. Default empty → identical to today.
- `lesson.build` gains an optional `directive: str = ""`: appended to the prompt so
  sentences emphasize the focus/pattern. Empty → byte-identical prompt to today.
- `main.py` Dutch branch (behind `DUTCH_COACH_ENABLED`): detect struggling → if any,
  call `coach.plan` → pass `focus_ids` as `force_review_ids` and `directive` into the
  builder. Fully guarded like the rest of the Dutch branch: any coach failure logs
  and falls back to mechanical selection so the lesson always ships.

## 5. Human on the loop (audit + override)

- **Log:** every plan appended to `storage/dutch_coach_log.md` (date, focus words,
  directive, reason) — the same audit trail the alias curator keeps.
- **Override:** `DUTCH_COACH_ENABLED = False` is the hard rollback. For a single bad
  call, the learner edits/clears the day's focus; persistent "don't drill X this way"
  is a later refinement, not v1. (No denylist needed at first — unlike aliases, a
  coach focus is per-day and self-expiring, not a sticky permanent merge.)

## Config (`config.py`)

```python
DUTCH_COACH_ENABLED   = True   # False -> mechanical selection only (rollback)
DUTCH_COACH_MIN_MISSES = 2     # misses before a word counts as "struggling"
DUTCH_COACH_MAX_FOCUS  = 3     # cap on focus words per lesson (targeted, not a dump)
```

## Testing (offline, canned `chat_fn`)

- struggle detection: a word with `recall_wrong=3, recall_right=1` is struggling;
  `1/0` (one slip) is not; no-data word is not.
- cap + subset: coach plan returns at most MAX_FOCUS; ids outside the struggling set
  are dropped.
- cold start: empty struggling set → coach not called, selection identical to today.
- wiring: `force_review_ids` guarantees a non-due word is taught; empty `directive`
  leaves the prompt unchanged (regression guard on existing lesson tests).
- rollback: `DUTCH_COACH_ENABLED=False` → byte-identical to current Dutch lesson.
- Scope pytest to `dutch` (+ `storage`); ruff clean.

## Acceptance criteria

- [ ] A word the learner repeatedly fails is pulled into the lesson even when not due.
- [ ] The lesson prompt carries a focus directive derived from the failure pattern.
- [ ] `DUTCH_COACH_ENABLED=False` / no recall data = identical to current behavior.
- [ ] Every plan is logged; coach failure never blocks the daily lesson.
- [ ] At most `DUTCH_COACH_MAX_FOCUS` words; coach never invents vocabulary.

## Out of scope

- **CEFR A2→B1 auto-advancement** — separate, higher-stakes judgment (Day 33 flagged
  it); the recall data could inform it later.
- **Generating new vocabulary** — the curated bank stays the source of truth; the
  coach only selects/emphasizes within it.
- **Multi-user** — owner-only personal loop, like the recall feedback; generalizing
  waits for the personalization track ([[dutch-personalization-multiuser]]).
- **Persistent per-pattern overrides / denylist** — per-day focus is self-expiring;
  add only if a bad emphasis recurs.