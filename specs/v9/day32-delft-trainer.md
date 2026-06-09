# v9 / Day 32 — Interactive Delft trainer on GitHub Pages

**Goal:** the MP3 + PDF cover the Delft method on the honor system; what they
cannot do is *enforce* it — reveal translations on tap, check typed answers, or
hold the learner to one listen in the hardest exercise. Add a static, client-side
**trainer page** to the existing GitHub Pages site that does all three. No
backend, no auth, no new infra: the daily run commits a lesson JSON; the page is
plain HTML/JS reading it.

This is the v9 counterpart of the dashboard: state is committed by the radar run,
Pages serves it, the browser does the interactivity.

---

## 1. `dutch_lesson.json` — committed by the daily run

Written next to the other dashboard state, containing everything the page needs:

```json
{
  "date": "2026-06-09",
  "theme": "tech",
  "cefr": "A2",
  "audio_url": "<RELEASES_AUDIO_BASE>/dutch-20260609.mp3",
  "new_words": [{"id": "...", "nl": "...", "en": "..."}],
  "sentences": [{"id": "...", "nl": "...", "en": "..."}],
  "dialogue":  [{"speaker": "A", "nl": "...", "en": "..."}],
  "cloze": {"lines": ["Ik heb een ___ (1)."], "answers": ["afspraak"]},
  "segments": [{"block": "A", "speaker": "MAYA", "nl": "...", "en": "...",
                "start_ms": 0, "end_ms": 3200}],
  "block_c": {"start_ms": 39833, "end_ms": 45947}
}
```

`segments` gives per-sentence timestamps into the single MP3 so the page can play
one sentence at a time (each carries its Delft block letter and translation);
`block_c` is the straight-through dialogue's span — what the one-chance exercise
plays. `audio_builder._assemble` already knows every segment's offset while
concatenating — `build()` gains an optional `timings_out` parameter (dev callers
pass nothing; behavior unchanged), which the Dutch build uses. The composition
lives in `dutch/trainer.py`; `cloze.extract()` provides the structured blanks the
markdown `render()` is also built on.

## 2. `dutch.html` — the trainer page (plain JS, no framework)

Mirrors the Delft phases as modes:

- **Phase 1 — listen & imitate:** sentence list; tap to play just that sentence
  (seek by timestamp), tap again to replay; translation hidden behind a tap;
  a transcript on/off toggle for steps 2 vs 4.
- **Phase 2a — fill from text:** the cloze rendered as input fields; instant
  checking against `answers`; no audio.
- **Phase 2b — one-chance listening:** the page plays Block C **once** — the play
  button disables itself after a single use (the rule the PDF could only ask
  for, enforced) — then the remaining blanks unlock for typing.

Progress (which phases done, blanks right/wrong per word) is stored in
`localStorage` — per-device, no server, no PII leaving the browser. A small
recall-rate readout per word is the first real *learning monitoring* surface.

## 3. Delivery hook

The daily Telegram/email lesson gains one line: a "🎧 Train this lesson" link to
`<SITE_URL>dutch.html`. The page always shows the latest committed lesson (and
can grow a date picker later, same pattern as the dashboard's archive).

---

## Out of scope

- Accounts, sync across devices, or any server-side state (localStorage only).
- Feeding results back into spaced repetition (Day 33).
- Recording the learner's voice (browser-possible, but a separate feature).
- Back-catalog of past lessons (latest-only first; archive later if wanted).
