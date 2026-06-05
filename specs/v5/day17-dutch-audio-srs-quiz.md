# v5 / Day 17 — Dutch audio + spaced repetition + recall quiz

**Goal:** make the Dutch lesson *stick* and *speak*. Three additions to the day-16
foundation, shipped together because all three change what the learner receives:
(1) a **spaced-repetition memory** so each day mixes new words with words *due for
review*; (2) a **Dutch audio MP3** (edge-tts Dutch voices) delivered and fed to the
podcast; (3) a **recall-quiz link** on *yesterday's* words. Reuses the existing
edge-tts pipeline, the SR constants, and the Perplexity deep-link pattern — no new
services or credentials.

---

## Part A — Spaced-repetition memory (`storage/dutch_memory.json`)

A new committed state file, mirroring `skill_memory.json` (and its graceful-degrade
load/save in `storage/state.py`). It is the source of truth the dashboard (day 18)
and podcast feed rebuild from with no API keys.

```json
{
  "version": 1,
  "cefr": "A2",
  "streak": 0,
  "last_run": "2026-06-04",
  "last_words": ["bestand", "wachtwoord"],
  "words": {
    "bestand": {"introduced": "2026-06-02", "reps": 2,
                "last_review": "2026-06-04", "due": "2026-06-08"}
  },
  "lessons": [
    {"date": "2026-06-04", "theme": "tech", "audio": "dutch-20260604.mp3",
     "words": ["bestand", "wachtwoord"], "summary": "files & passwords"}
  ]
}
```

### Storage helpers (in `storage/state.py`, beside the skill-memory ones)

```python
def load_dutch_memory() -> dict        # {"version":1,"cefr":...,"words":{},"lessons":[]}
def save_dutch_memory(memory: dict) -> None
def dutch_due_words(memory, today) -> list[str]   # ids whose due <= today
def record_dutch_lesson(memory, *, words, theme, audio="", summary="") -> dict
```

`record_dutch_lesson` is the SR update, run after delivery:

- **New words** (first time taught): `reps=1`, `introduced=today`,
  `due = today + DUTCH_SR_BASE_INTERVAL_DAYS`.
- **Reviewed words**: `reps += 1`,
  `due = today + round(DUTCH_SR_BASE_INTERVAL_DAYS * DUTCH_SR_SPACING_FACTOR ** (reps-1))`.
- Sets `last_review=today` on every taught word, appends a `lessons[]` entry, stamps
  `last_words` (today's ids — the quiz target for *tomorrow*), bumps `streak` if
  `last_run` was yesterday else resets it to 1, and sets `last_run=today`.

### Config additions (`config.py`)

```python
DUTCH_SR_BASE_INTERVAL_DAYS = 1     # first review one day after introduction
DUTCH_SR_SPACING_FACTOR = 2.2       # widening: ~1, 2, 5, 11, 24 ... days
DUTCH_REVIEW_WORDS_MAX = 6          # cap on due words pulled into a morning
```

Shorter base than the dev track's `SR_BASE_INTERVAL_DAYS` (7): vocabulary needs
tighter early spacing than concept lessons.

### Selection now reads memory (replaces day-16 `wordlist.select`)

`dutch/wordlist.py` gains:

```python
def select_for_today(words, memory, today, *, theme, new_count, review_max) -> tuple[list[dict], list[dict]]:
    """Return (new_words, review_words).
    review_words: entries whose id is due today (oldest due first), up to review_max.
    new_words:    first `new_count` themed words never introduced (id not in memory)."""
```

`dutch/lesson.py:build()` takes both groups: new words are taught with full
example sentences; review words appear in the dialogue and a compact "review" line so
they resurface in context. The LLM still only writes sentences around **given** words.

---

## Part B — Dutch audio MP3 (edge-tts Dutch voices)

### Voices (`config.py`)

```python
DUTCH_VOICE_A = "nl-NL-MaartenNeural"   # speaker A
DUTCH_VOICE_B = "nl-NL-ColetteNeural"   # speaker B
DUTCH_TTS_RATE = "-10%"                 # slower than native, A2-friendly
```

### Reuse `learnx/audio_builder.py` by injecting the voice map

`audio_builder.build` currently resolves voice/rate from the module-level English
maps keyed by `ALEX`/`MAYA` (`learnx/audio_builder.py:33`). Generalize minimally and
back-compatibly:

```python
async def build(lines, out_path, *, voices=None, rates=None) -> None:
    voices = voices or _VOICE     # default = existing English map
    rates  = rates  or _RATE
```

`_render_segment` reads from the passed maps. Existing dev calls (no kwargs) are
unchanged; Dutch passes `voices={"A": DUTCH_VOICE_A, "B": DUTCH_VOICE_B}`,
`rates={"A": DUTCH_TTS_RATE, "B": DUTCH_TTS_RATE}`.

### `dutch/audio.py`

```python
def build(dlesson: DutchLesson, out_path: str) -> None:
    """Turn the Dutch dialogue (+ a spoken run of the new words) into one MP3 via
    audio_builder, using the Dutch voices/rate. Speakers map A->voice A, B->voice B."""
```

The dialogue's `speaker` (`A`/`B`) maps to the two Dutch voices; the rendered file is
`output/dutch-YYYYMMDD.mp3` (date-stamped like the dev lesson). Word-only lines are
voiced by speaker A so the learner hears each new word in isolation before the dialogue.

### Delivery of the audio

- **Telegram**: the day-16 Dutch `sendMessage` becomes a **second `sendAudio`** — the
  Dutch MP3 with the Dutch text as caption and the quiz button (Part C) as inline
  keyboard. Two audio messages each morning (dev + Dutch).
- **Email**: attach the Dutch MP3 as a **second attachment** in `_build_message`
  (loop over present mp3 paths) and keep the rendered Dutch HTML section from day 16.
  One email, two MP3s.

### Podcast / Release upload

The radar workflow already uploads the dev MP3 as a `lessons` Release asset. Add the
Dutch MP3 to the same upload step (any `output/*.mp3` from this run), so its
`RELEASES_AUDIO_BASE` URL exists for the feed (day 18 wires it into `podcast.xml`).

---

## Part C — Recall quiz on yesterday's words (`delivery/followup.py`)

A **third** Perplexity deep link, additive — the dev `perplexity_url()` and
`quiz_url()` are untouched.

```python
def dutch_quiz_url(words: list[dict]) -> str:
    """Quiz the learner on the GIVEN Dutch words (yesterday's set). Embeds the
    word list (nl + en) as grounding so Perplexity needs no external fetch."""
```

Seeded query (the single tunable line that sets the format — translation + usage
recall, one at a time):

> "Quiz me on these Dutch words I learned yesterday: {nl — en list}. Ask me one at a
> time: alternate 'how do you say X in Dutch?' and 'what does <Dutch word> mean?',
> plus one short fill-in-the-blank Dutch sentence. Wait for my answer, then correct
> me with the right word and article (de/het). Start with question one."

Targets **`memory["last_words"]`** (the prior run's ids → their curated entries),
genuine spaced retrieval. Absent on day one → the button simply isn't rendered, same
pattern as the dev quiz. The button rides the Telegram Dutch `sendAudio` keyboard and
the email Dutch section.

---

## `main.py` wiring (extends day 16)

```python
if config.DUTCH_ENABLED:
    try:
        dmem = load_dutch_memory()
        theme = dutch.theme_for(date.today())
        new_w, review_w = dutch.select_for_today(
            dutch.load(), dmem, date.today(), theme=theme,
            new_count=config.DUTCH_NEW_WORDS_PER_DAY,
            review_max=config.DUTCH_REVIEW_WORDS_MAX)
        topic = skill["skill"] if theme == "tech" and config.DUTCH_THEME_TECH_TIE_IN else None
        dlesson = dutch_lesson.build(new_w + review_w, theme=theme, topic=topic)
        dpath = str(OUTPUT_DIR / f"dutch-{date.today():%Y%m%d}.mp3")
        asyncio.run(dutch_audio.build(dlesson, dpath))
        prev_words = [w for w in dmem.get("words", {}) if ...]  # entries for last_words
        lesson["dutch"] = {
            "markdown": dlesson.markdown, "mp3_path": dpath,
            "quiz_words": _entries_for(dmem.get("last_words", [])),
        }
    except Exception as exc:
        print(f"[dutch] build failed: {exc}")
```

After delivery (beside `record_lesson`):

```python
record_dutch_lesson(dmem, words=[w["id"] for w in new_w + review_w],
                    theme=theme, audio=Path(dpath).name,
                    summary=dlesson.summary)
save_dutch_memory(dmem)
```

`last_words` is read **before** `record_dutch_lesson` overwrites it (the quiz tests
the previous run), the same ordering the dev quiz uses with `previous_lesson`.

---

## Testing (offline)

- `load_dutch_memory` / `save_dutch_memory`: roundtrip; corrupt/missing → default
  `{"version":1,...}`.
- `dutch_due_words`: returns only ids with `due <= today`, oldest first, capped.
- `record_dutch_lesson`: new word gets `reps=1` + base due; a second exposure widens
  the interval; `streak` increments on consecutive days and resets after a gap;
  `last_words` is set to today's ids; a `lessons[]` entry is appended.
- `select_for_today`: excludes already-introduced ids from new; includes due ids in
  review; respects `new_count`/`review_max` and theme.
- `audio_builder.build`: with no kwargs uses the English map (regression); with Dutch
  `voices`/`rates` it requests the Dutch voices (assert via a mocked
  `edge_tts.Communicate`).
- `dutch_quiz_url`: returns a `perplexity.ai/search/new` URL whose decoded query
  contains the words and "one at a time"; empty `words` → callers don't render it.
- `email_sender`: two attachments when a Dutch mp3 is present; Dutch quiz button
  rendered only when `quiz_words` is non-empty. `telegram_sender`: Dutch `sendAudio`
  with quiz keyboard when present.
- Dev-track regression: `perplexity_url` / `quiz_url` outputs unchanged.

edge-tts/SMTP/Telegram/network are mocked — no real audio render or send in tests.

## Acceptance criteria

- [ ] `dutch_memory.json` tracks per-word SR due dates, CEFR, streak, and a lesson
      archive; each morning mixes new + due-for-review words.
- [ ] A Dutch MP3 (Dutch voices, slower rate) is built, delivered on both channels,
      and uploaded as a Release asset.
- [ ] A "Quiz me in Dutch" Perplexity button targets *yesterday's* words; no-op on
      day one; dev follow-up/quiz links unchanged.
- [ ] A Dutch failure is isolated; the dev lesson still ships.
- [ ] Offline tests pass; ruff clean.

## Out of scope

- Dashboard Dutch tab + feeding the Dutch MP3 into `podcast.xml` → **day 18**.
- CEFR auto-advance, audio answer-checking, grammar drills → later.
