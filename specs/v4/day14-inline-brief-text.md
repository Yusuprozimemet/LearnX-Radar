# v4 / Day 14 — Inline the brief text into the Perplexity deep link

**Goal:** make the "Ask follow-ups" and "Quiz me" buttons actually work.
Perplexity does **not** reliably fetch an external URL, so the previous design —
a query that said *"read this brief: <raw github URL>"* — left Perplexity with no
grounding and it would just decline or improvise. Embed the brief **text** in the
query instead of linking to it.

## The change

`delivery/followup.py` builds the same `perplexity.ai/search/new?q=…` deep link,
but the query now contains the condensed brief text rather than a URL:

- `perplexity_url(skill, brief_md)` / `quiz_url(skill, brief_md)` take the brief
  **markdown text** (was: the brief **filename**).
- `_condense(brief_md, limit)` flattens the markdown — strips `#` headings and
  `*`/`-` bullets, collapses whitespace to single-line prose — and trims to
  `config.FOLLOWUP_BRIEF_CHARS` (default **1200**), cutting at a sentence
  boundary when one falls late enough, else hard-trim + ellipsis. This keeps the
  embedded context dense and the whole URL bounded.

### Why a length budget

The deep link rides in a **Telegram inline-keyboard button URL**, which has a
practical length ceiling; a full ~2.5–3.2 KB brief, URL-encoded (~1.3–3× per
char), would risk the Telegram API rejecting the button and failing the
`sendAudio` call. At `FOLLOWUP_BRIEF_CHARS = 1200` the real briefs produce
follow-up URLs ~1.9 KB and quiz URLs ~2.1 KB — comfortably under the limit while
still giving Perplexity the title, "why", "what you'll learn", and the start of
the core ideas. Email has no such limit; one budget covers both for simplicity.
A too-long Telegram URL is also non-fatal: `main()` catches per-sender send
failures, so email still goes out.

## Plumbing

The quiz targets the **previous** lesson, and the lesson dict only carried that
brief's *filename*. `main()` now loads its text:

```python
prev = previous_lesson(memory)
if prev and prev.get("brief"):
    prev_brief_md = load_brief(prev["brief"])
    if prev_brief_md:
        lesson["quiz_skill"] = prev["skill"]
        lesson["quiz_brief_md"] = prev_brief_md   # text, not filename
```

Both senders read the text keys and gate the button on them:

- follow-up button ← `lesson["brief_md"]` (already set when the brief is written)
- quiz button ← `lesson["quiz_brief_md"]` (loaded above; empty/missing ⇒ no button)

`config.BRIEFS_RAW_BASE` is retained (briefs stay committed as the full source of
truth and are referenced from docs/dashboard) but is no longer part of the deep
link.

## Testing (offline)

- `perplexity_url` / `quiz_url` embed the brief **text** (assert a brief phrase is
  present) and contain **no** `raw.githubusercontent.com` link.
- `_condense` trims a long brief to the budget and flattens newlines.
- Telegram/email button gates use `brief_md` / `quiz_brief_md`; the no-brief and
  no-prior cases still render no button.

## Acceptance criteria

- [x] Follow-up and quiz deep links seed Perplexity with the brief text, no URL
      to scrape.
- [x] Generated URLs stay within Telegram's inline-button limit (real briefs
      ≈1.9–2.1 KB).
- [x] Quiz still targets the previous lesson; no button when its brief is absent.
- [x] Offline tests pass; ruff clean.

## Out of scope

- Per-channel budgets (email could embed the full brief) — one global budget is
  enough and keeps the two senders identical.
- A real chat integration (Perplexity API) instead of a prefilled web query —
  still out of scope; the deep link needs no credential.
