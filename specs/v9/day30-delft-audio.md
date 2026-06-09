# v9 / Day 30 — Delft-format Dutch audio (listen → repeat → listen again)

**Goal:** the daily Dutch MP3 currently plays words + dialogue straight through —
passive listening only. Restructure it into the **Delftse methode** Phase 1 shape:
every sentence is followed by a silent pause sized for the learner to repeat it
aloud, then the sentence plays again for self-checking. The lesson stops being
something you hear and becomes something you *say*.

The Delft method's input phase, mapped onto one MP3:

| Delft step | Audio |
|---|---|
| 1. Sentence → repeat → self-check | Blocks A & B (sentence → pause → sentence again) |
| 2. Whole text, with transcript | Block C, first listen (PDF open) |
| 3. Sentence repeat, no transcript | Replay Blocks A & B (PDF closed) |
| 4. Whole audio, no transcript | Replay Block C (PDF closed) |

Steps 3–4 are replays — the listener's behavior, not new audio. A short
practice-instructions section in the lesson markdown tells them how.

---

## 1. `DialogueLine.pause_after_factor` (learnx/models.py)

A new optional field, default `0.0`:

```python
pause_after_factor: float = 0.0  # silence AFTER this line = factor x line duration
```

The repeat-pause must scale with the sentence (a 2s sentence needs ~3s to repeat;
a 6s one needs ~9s), and the duration is only known after TTS renders the segment
— which `RenderedSegment.duration_ms` already captures. So the factor rides on the
line; assembly resolves it.

## 2. Proportional silence in `audio_builder._assemble`

After appending a segment whose line has `pause_after_factor > 0`, append
`max(int(duration_ms * factor), DUTCH_DELFT_MIN_PAUSE_MS)` of silence. The
*pre-line* gap logic (`_gap_ms`) is untouched, except a line following a
proportional pause gets no extra pre-gap (the pause already separates them).

Dev-track callers never set the field → factor 0.0 → byte-identical output.
No flag needed at this layer; the field is the opt-in.

## 3. Delft block structure in `dutch/audio.py to_lines()`

Behind `DUTCH_DELFT_AUDIO` (rollback switch — `False` restores the v5 layout):

- **Block A — vocabulary (unit 0):** per new word:
  word (ALEX) → example sentence (MAYA, pause-after `FACTOR`) → sentence again
  (MAYA, pause-after `0.5`). Listen → repeat aloud in the pause → hear it again.
- **Block B — dialogue, sentence by sentence (unit 1):** per dialogue line:
  line (pause-after `FACTOR`) → line again (pause-after `0.5`). Speaker voices as
  today (A→ALEX, B→MAYA).
- **Block C — dialogue straight through (unit 2):** the dialogue once more with
  only the natural turn gaps — the "whole text" listen for Delft steps 2 and 4.

With 4 new words + a ~8-line A2 dialogue this lands around 6–9 minutes —
intentional: the pauses ARE the exercise.

```python
DUTCH_DELFT_AUDIO = True        # False -> legacy v5 audio layout (rollback)
DUTCH_DELFT_PAUSE_FACTOR = 1.5  # repeat-pause = 1.5x the sentence duration
DUTCH_DELFT_MIN_PAUSE_MS = 1200 # floor so one-word sentences still leave time
```

## 4. Practice instructions in the lesson markdown (`dutch/lesson.py`)

A short "**Zo oefen je (how to practice)**" section after the header, telling the
learner the four Delft steps and which block/replay each one is. Rendered in the
same bold-Dutch / italic-English convention, so it flows into the existing PDF,
email, and Telegram delivery with no sender changes.

---

## Out of scope

- Recording yourself / playback comparison (needs an interactive surface — Day 32).
- Per-sentence seeking / timestamps (Day 32's trainer page).
- Changing the dev-lesson audio in any way.
- Splitting the lesson into multiple MP3 files (one file stays one feed item /
  one Telegram message / one release asset).
