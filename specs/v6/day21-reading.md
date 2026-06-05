# v6 / Day 21 — Reading (comprehensible input)

**Goal:** rehearse the *Lezen* exam skill and consolidate vocabulary far faster than
isolated words: a short daily Dutch text scaled to the learner's level (A2→B1), built
**mostly from words already in `dutch_memory.json`** plus a few new ones (i+1), with
an English gloss and 1–2 comprehension questions.

---

## Why "mostly known words" (the i+1 principle)

Reading consolidates vocabulary only when the text is *comprehensible* — roughly 90%+
known words with a little new. So the generator is **constrained by the learner's
memory**: it is handed the words the learner has already seen (and today's new ones)
and told to write a natural short text using mainly those. This reuses the v5
"constrain the LLM with our data" pattern; the grammar stays at the current CEFR.

## Module: `dutch/reading.py`

```python
@dataclass
class Reading:
    title_nl: str
    text_nl: str
    text_en: str            # English gloss of the whole text
    questions: list[dict]   # [{"q_nl", "a_nl"}] 1-2 comprehension Qs
    markdown: str           # rendered 🇳🇱-block reading section

def build(known_words: list[dict], new_words: list[dict], *,
          cefr: str, theme: str, topic: str | None = None, chat_fn=llm.chat) -> Reading:
    """One LLM call: a ~5-8 sentence A2 (or B1) text that uses mainly `known_words`,
    naturally introduces `new_words`, fits `theme` (and `topic` on tech days),
    plus a gloss and 1-2 questions. Returns strict JSON parsed into Reading."""
```

Constraints in the prompt **and** checked after: target length by CEFR (A2 shorter,
simpler sentences; B1 longer, subordinate clauses), reuse the supplied vocabulary,
keep new words to the day's set. If parsing fails the reading is simply omitted (the
vocab lesson still ships) — same degrade-don't-crash stance as the lesson builder.

### Where `known_words` comes from

`dutch_memory["words"]` keys → their curated entries (cap to a recent/frequent slice
so the prompt stays small, e.g. the last ~60 introduced). On early days with little
history, the text leans on the day's new words and the most common seed words.

## Delivery + dashboard

- The reading (title, Dutch text, a collapsible English gloss, the questions) is
  appended to the Dutch block under `🇳🇱 Lezen`. In email it renders as HTML; in
  Telegram it's part of the Dutch text message (trim if over caption limits — send as
  a follow-up `sendMessage` if needed).
- The audio (day 17) can optionally **also voice the reading** so *Luisteren* and
  *Lezen* share one MP3 — a config flag `DUTCH_READING_IN_AUDIO`.
- Dashboard Dutch tab: a "Readings" count and the latest reading in an expandable card.

## `main.py`

Within the guarded Dutch block, after vocab selection:

```python
known = _entries_for_recent(dmem, limit=60)
reading = dutch_reading.build(known, new_w, cefr=dmem.get("cefr","A2"),
                              theme=theme, topic=topic)
lesson["dutch"]["reading"] = reading.markdown
```

## Testing (offline, mocked `chat_fn`)

- `reading.build` (canned JSON): returns a Reading with text, gloss, and questions;
  the prompt contains the supplied known/new words and the CEFR length instruction.
- Parse failure → callers get no reading, no exception.
- CEFR switch: A2 vs B1 changes the length/complexity instruction in the prompt.
- Delivery: the reading renders in the Dutch block when present; absent cleanly when
  not.

## Acceptance criteria

- [ ] A short daily Dutch text built mainly from known words + the day's new words,
      with English gloss and 1-2 comprehension questions, ships in the Dutch block.
- [ ] Length/complexity scales with CEFR (A2→B1).
- [ ] Optional: the reading is voiced into the Dutch MP3 behind a config flag.
- [ ] Reading failure degrades gracefully; vocab lesson still ships.
- [ ] Offline tests pass; ruff clean; committed pipeline state untouched.

## Out of scope

- Auto-grading reading answers (v7). Questions are self-check, answers shown.
- Authentic external texts (news RSS) — kept generated-from-known-words to stay
  comprehensible and copyright-free, consistent with the word-bank decision.
