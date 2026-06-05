# v5 / Day 16 — Dutch coach foundation (curated wordlist + daily text lesson)

**Goal:** alongside the dev lesson, deliver a small **A2 Dutch** lesson every
morning — a themed set of words with example sentences and a short dialogue —
appended to the existing email and sent as a Telegram message. Vocabulary is
**anchored to a curated, pre-verified word list**; the LLM only writes sentences
around fixed words, never invents vocabulary.

This day ships the foundation: the word bank, the lesson builder, config, and the
text delivery. **No audio and no memory yet** — those are day 17. So day 16 picks
words deterministically by date (no spaced repetition), which keeps it fully
testable offline and proves the pipeline end to end.

---

## Why a frozen word bank (the central design choice)

An LLM asked to pick new Dutch words *fresh every morning* will, over hundreds of
runs, occasionally emit a wrong gender (`de`/`het`), a non-word, or a false friend —
and the learner has no way to know. The fix is **not** to ban the LLM from authoring
the words; it is to author them **once, review them once, and freeze them**:

- The word bank (`dutch/wordlist.json`) is **generated once** by the LLM from the
  target level + themes (see "Sourcing" below), reviewed by a human, then
  **committed and treated as static data**. The daily run only *selects from* it —
  it never asks the LLM for new vocabulary at run time.
- This is the same "trust the data, distrust the live generation" stance as the v4
  decision to ground the quiz in the committed brief rather than free-associate.

**Why generate it rather than import a frequency list:** a self-generated list has
**no copyright/licensing exposure** — nothing is copied from an external dataset
(individual word→gloss facts aren't copyrightable, but a wholesale list's selection
can be; generating our own removes the question entirely). The one-time human review
is what guarantees correctness, so generation cost is paid once, not daily.

## Sourcing the word bank (one-time, offline)

A one-off helper — **not part of the daily run** — produces the committed file:

```
dutch/build_wordlist.py    # run manually, e.g. `python -m dutch.build_wordlist`
```

It calls the existing `learnx/llm.py` client in batches (per theme, per word-class)
with a strict prompt — "produce N A2 Dutch words on <theme>; for each give the word
with its article, English gloss, part of speech; return JSON; no proper nouns, no
duplicates" — merges/dedupes the batches by `id`, and writes `dutch/wordlist.json`.

Then a **human review pass** (the correctness guarantee): skim the list, fix any
`de`/`het` or spelling slips, drop oddities. After that the file is frozen; growing
it later is a re-run + review of a new batch, or a hand edit. The daily pipeline
never regenerates it.

> The seed list can equally be authored by hand or pair-written with the assistant;
> `build_wordlist.py` just makes regeneration repeatable. Either way the committed
> JSON is the reviewed source of truth.

---

## New module: `dutch/`

```
dutch/
  __init__.py
  wordlist.json        # the frozen A2 word bank (committed source of truth)
  build_wordlist.py    # ONE-TIME generator (manual run, not in the daily pipeline)
  wordlist.py          # load + select today's words (deterministic on day 16)
  lesson.py            # build the daily Dutch lesson (one LLM call)
  prompts/
    lesson.txt         # the sentence/dialogue prompt (words are injected, fixed)
  prompt_loader.py     # mirrors radar/prompt_loader.py (or reuse it)
  tests/
    __init__.py
    fixtures/
      wordlist_sample.json
```

### `dutch/wordlist.json`

A versioned list of pre-verified A2 entries. Each entry is self-contained and keyed
by a stable `id` (used by day 17's memory):

```json
{
  "version": 1,
  "words": [
    {"id": "vergadering", "nl": "de vergadering", "en": "the meeting",
     "pos": "noun", "theme": "everyday", "cefr": "A2"},
    {"id": "afspraak", "nl": "de afspraak", "en": "the appointment",
     "pos": "noun", "theme": "everyday", "cefr": "A2"},
    {"id": "bestand", "nl": "het bestand", "en": "the file",
     "pos": "noun", "theme": "tech", "cefr": "A2"},
    {"id": "wachtwoord", "nl": "het wachtwoord", "en": "the password",
     "pos": "noun", "theme": "tech", "cefr": "A2"}
  ]
}
```

- `nl` includes the article for nouns (gender is the thing learners get wrong, so it
  is baked into the verified data, never asked of the LLM).
- `theme` is `everyday` or `tech`. Seed batch target: **~120–200 words** (enough to
  not repeat for weeks once day 17's spacing kicks in); the file can grow anytime.
- The list is committed and reviewed like code — generated once by
  `build_wordlist.py`, human-reviewed, then frozen. Adding words is a data PR, never
  a runtime LLM call.

### `dutch/wordlist.py`

```python
def load(path: Path = WORDLIST_FILE) -> list[dict]:
    """Load and validate the curated word bank; [] if missing/corrupt (never crash)."""

def theme_for(day: date) -> str:
    """Alternate themes by date so consecutive mornings differ.
    'tech' on even ordinals, 'everyday' on odd (day.toordinal() % 2)."""

def select(words: list[dict], *, theme: str, count: int, offset: int = 0) -> list[dict]:
    """Pick `count` words of `theme` in list order, starting at `offset`.
    Day 16 derives a deterministic offset from the date so the set rotates and is
    reproducible in tests; day 17 replaces this with memory-driven selection."""
```

Day-16 selection is intentionally simple and stateless: today's theme + a
date-derived offset → a stable slice. (Day 17 swaps `select` for "new words not yet
introduced + words due for review", reading `dutch_memory.json`.)

### `dutch/lesson.py`

```python
@dataclass
class DutchLesson:
    theme: str
    words: list[dict]          # the exact curated entries taught today
    sentences: list[dict]      # [{"id", "nl", "en"}] — one example per word
    dialogue: list[dict]       # [{"speaker", "nl", "en"}] short A2 exchange
    markdown: str              # rendered 🇳🇱 block for email/Telegram

def build(words: list[dict], *, theme: str, topic: str | None = None,
          chat_fn=llm.chat) -> DutchLesson:
    """One LLM call returns sentences + dialogue for the GIVEN words. `topic` is the
    day's dev skill, woven into a tech-themed lesson for the connective hook; ignored
    on everyday days. Reuses learnx/llm.py — no new provider."""
```

Key constraints, enforced in the prompt **and** verified in code after the call:

- The LLM is given the exact word list and told: **use only these words as the new
  vocabulary; do not introduce other words as "new"; keep everything A2; output
  JSON**. (Everyday connective words in the sentences are fine — the rule is "don't
  present new vocab as taught".)
- `build()` parses the JSON and **drops any sentence/dialogue line that doesn't map
  back to a provided word id**; if the model returns nothing usable for a word, that
  word still appears with its verified `nl`/`en` gloss and no example (correct data
  always survives a bad generation). This is the same "trust the data, distrust the
  generation" guard as the curated-list decision.

### `dutch/prompts/lesson.txt`

Injected placeholders: `{theme}`, `{topic}`, `{words}` (the id + nl + en list).
The prompt instructs: A2 level, short sentences, natural Dutch, one example sentence
per provided word, then a 4–6 line two-speaker dialogue (`speaker` is `A`/`B`) that
reuses the words; **return strict JSON** of the shape `build()` parses; on tech days
center the scenario on `{topic}`. No new vocabulary may be presented as taught.

---

## Config additions (`config.py`)

A `DUTCH_*` block alongside `SOURCE_WEIGHTS` / personalization, so all tuning lives
in one place:

```python
# --- Dutch coach (v5) ---
DUTCH_ENABLED = True                 # master switch; False = skip the whole track
DUTCH_CEFR_START = "A2"              # starting level (auto-advances in a later day)
DUTCH_NEW_WORDS_PER_DAY = 4          # new words introduced each morning
DUTCH_THEME_TECH_TIE_IN = True       # on tech days, tie the lesson to the dev topic
```

(Day 17 adds the audio-voice and spaced-repetition constants; not needed yet.)

No new env vars / secrets — the LLM is the existing NVIDIA NIM client.

---

## Delivery (additive, both channels)

The Dutch block is rendered from `DutchLesson.markdown`. Both senders already take
the `lesson` dict; add an optional `lesson["dutch"]` carrying the rendered block
(and, from day 17, the audio path + quiz URL). When absent, delivery is byte-for-byte
unchanged.

- **`email_sender`** — append the Dutch block under a `🇳🇱 Dutch (A2)` heading at the
  end of `_render_html`, reusing `_markdown_to_html`. One email, dev + Dutch.
- **`telegram_sender`** — since a Telegram message carries one audio + caption, the
  Dutch lesson is a **separate `sendMessage`** (plain text, no parse_mode, same
  rationale as the existing caption: Dutch/code chars break Markdown). A small
  `send_text(dutch_md)` helper next to `send()`; on day 16 it is the only Dutch
  delivery, on day 17 it becomes a second `sendAudio` with this text as caption.

---

## `main.py` wiring

After the dev `lesson` dict is built and before delivery, one guarded block (same
per-stage `try/except` discipline as `_scrape`/dashboard — a Dutch failure must
never kill the dev run):

```python
if config.DUTCH_ENABLED:
    try:
        theme = dutch.theme_for(date.today())
        words = dutch.select(dutch.load(), theme=theme,
                             count=config.DUTCH_NEW_WORDS_PER_DAY, offset=...)
        topic = skill["skill"] if (theme == "tech" and config.DUTCH_THEME_TECH_TIE_IN) else None
        dlesson = dutch_lesson.build(words, theme=theme, topic=topic)
        lesson["dutch"] = {"markdown": dlesson.markdown}
    except Exception as exc:
        print(f"[dutch] build failed: {exc}")
```

Delivery already iterates the senders; they pick up `lesson["dutch"]` when present.

---

## Testing (offline, mocked `chat_fn`)

- `wordlist.load`: parses the sample fixture; returns `[]` for missing/corrupt file.
- `wordlist.theme_for`: alternates across consecutive dates (even/odd ordinal).
- `wordlist.select`: returns `count` words of the requested theme, in order, and the
  date-derived offset rotates the slice deterministically.
- `lesson.build` (mocked LLM returning canned JSON): produces one sentence per word;
  **drops** a hallucinated line whose id isn't in the input; a word the model
  skipped still appears with its verified gloss.
- `lesson.build` prompt text contains the "use only these words / A2 / strict JSON"
  instruction and the injected words.
- `email_sender`: Dutch heading + words render when `lesson["dutch"]` is set; output
  unchanged when it's absent (regression guard).
- `telegram_sender.send_text`: posts the Dutch markdown; no-op/skip when empty.

No network: edge-tts and SMTP/Telegram are not touched on day 16 (text only; audio
is day 17).

---

## Acceptance criteria

- [ ] A curated `dutch/wordlist.json` (seed batch, themed, with verified articles).
- [ ] Each morning a themed A2 Dutch block (words + example sentences + short
      dialogue) is appended to the email and sent as a Telegram message.
- [ ] Themes alternate everyday/tech day-to-day; tech days reference the dev topic.
- [ ] The LLM never introduces new vocabulary; words always come from the list, and
      a bad generation degrades to the verified gloss rather than a wrong word.
- [ ] A Dutch failure prints and is skipped; the dev lesson still ships.
- [ ] Offline tests pass; ruff clean.

## Out of scope (handled later)

- Dutch audio MP3, spaced-repetition memory, the recall-quiz link → **day 17**.
- Dashboard Dutch tab + podcast-feed integration → **day 18**.
- CEFR auto-advance (A2→B1) and grammar drills → a later day.
