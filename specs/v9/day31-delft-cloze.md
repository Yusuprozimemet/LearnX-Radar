# v9 / Day 31 — Cloze exercise (Delft Phase 2: production)

**Goal:** the Dutch track delivers input (audio + transcript) but no *production*
step — the Delftse methode's Phase 2, where the learner must generate the words
themselves. Add a deterministic fill-in-the-blanks (cloze) section to the daily
lesson: today's **new words** are blanked out of the dialogue and example
sentences, with a numbered answer key at the end. Two difficulty levels, per the
method: fill from memory first; then replay audio Block C **once** and fill the
rest while listening.

---

## 1. `dutch/cloze.py` — deterministic blanking, no LLM

The pipeline already knows exactly which words are new today, so blanking is pure
string work (same correct-by-design stance as the wordlist: nothing generated,
nothing to hallucinate):

- `render(new_words, sentences, dialogue) -> str` returns the markdown section,
  or `""` when nothing could be blanked (the section simply doesn't render —
  same degrade pattern as the lesson's other optional parts).
- Matching: word-boundary, case-insensitive search for each new word's `nl` form
  inside the example sentences and dialogue lines. Leading articles (`de `/`het `)
  are stripped from the word before matching — the bank stores nouns with their
  article, but inside a sentence the noun appears with any (or no) article.
- Each first occurrence becomes `___ (n)` with a running blank number; the answer
  key lists `n. woord` at the bottom. A new word that never appears in the text
  is skipped, not forced.
- Inflection (e.g. bank form `werken`, dialogue `werkt`) is NOT chased — exact
  form match only. A missed blank degrades to a normal sentence, never a wrong
  blank. Revisit only if real lessons show too few blanks.

## 2. Section in the lesson markdown (`dutch/lesson.py`)

Behind `DUTCH_CLOZE_ENABLED` (default `True`), appended after the dialogue:

```
**Invuloefening (fill in the blanks)** — _Delft fase 2_
1. Vul eerst in uit je geheugen (fill from memory first).
2. Te moeilijk? Luister Blok C nog ÉÉN keer en vul de rest in
   (replay Block C once — one chance — and fill the rest).

- A: Ik heb morgen een ___ (1) bij de dokter.
- B: Hoe laat ___ (2) je?
...

_Antwoorden (answers):_ 1. afspraak · 2. begin
```

The answer key stays in the same document (the PDF is read on a phone; a separate
key would just be friction). Discipline is the learner's — the instruction makes
the intended order explicit.

Because it's part of `lesson.markdown`, the section flows into the existing PDF,
email, and Telegram delivery with zero sender changes.

```python
DUTCH_CLOZE_ENABLED = True  # False -> lesson markdown unchanged (rollback)
```

---

## Out of scope

- Checking the learner's answers (no interactive surface yet — Day 32).
- Blanking review words (only today's new words; review is the quiz's job).
- Morphological/inflected matching (exact form only, by decision above).
- The "one chance" rule being *enforced* — on paper it's an instruction;
  enforcement arrives with the trainer page (Day 32).
