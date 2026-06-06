# v8 / Day 27 — Public distribution (channel + PDF + waitlist)

**Goal:** turn the private cron (which delivered to one owner DM + email) into
something other people can subscribe to — without standing up an inbound server or
storing any subscriber PII. Three additive, independently-flagged, failure-isolated
pieces, all riding the existing daily run.

> **Privacy is the design constraint, not a feature.** We never store a subscriber
> list. Telegram holds channel membership; the waitlist form provider holds emails
> under consent. No new private datastore, no new PII in the repo.

---

## 1. Channel broadcast

`telegram_sender.send(lesson)` fans the same lesson out to:

- the **owner DM** (`TELEGRAM_CHAT_ID`) — unchanged behavior, and
- an optional **public channel** (`TELEGRAM_CHANNEL_ID`, e.g. `@learnradar`).

Decoupling the public product from the personal bot:

- `TELEGRAM_CHANNEL_BOT_TOKEN` is a **separate** public bot (e.g. `LearnRadarBot`)
  that admins the channel. `_token_for(chat_id)` picks the right token per target, so
  DM/quiz traffic stays on the personal bot.
- PDFs (below) are rendered **once** and reused across targets.
- Every target is wrapped in its own `try/except` — one failing post never blocks the
  others or the rest of the run.

**Degradation:** `TELEGRAM_CHANNEL_ID` unset → delivery goes to the DM only, exactly
as before.

---

## 2. Full-lesson PDF

Audio captions cap at **1024 chars**, which truncated the (longer) Dutch dialogue and
hid the formatted brief. So attach the **complete lesson as a PDF**:

- `delivery/pdf.py` renders the brief markdown → HTML → PDF via **`xhtml2pdf`**
  (pure-Python; the CI/cron runners install `libcairo2-dev` + `pkg-config` for its
  build).
- Sent via Telegram `sendDocument` alongside the audio.
- `config.TELEGRAM_PDF_ENABLED` (default `True`); `False` → legacy caption-only.

---

## 3. Weekly waitlist CTA

A recurring call-to-action inviting subscribers to the **personalized-lessons**
waitlist:

- `telegram_sender.post_waitlist()` posts `config.WAITLIST_MESSAGE` (with
  `WAITLIST_URL`) to the **channel only**, on `WAITLIST_POST_WEEKDAY` (Thu=3).
- Wired into `main()` **before** the quiet-day early-return, so it still fires on a
  day with no new lesson.
- Links a hosted form (Tally, `https://tally.so/r/WOqPdP`) — **we store nothing**; the
  form provider holds submissions under consent (see `privacy.html`).
- `config.WAITLIST_ENABLED` / empty `WAITLIST_URL` → skipped.

---

## Config added

```python
TELEGRAM_CHANNEL_ID          # public channel id/handle; unset -> DM-only
TELEGRAM_CHANNEL_BOT_TOKEN   # separate public bot admining the channel
TELEGRAM_PDF_ENABLED = True  # attach full-lesson PDF via sendDocument
WAITLIST_ENABLED = True
WAITLIST_URL                 # hosted form link (Tally); empty -> skip
WAITLIST_POST_WEEKDAY = 3    # Thu
WAITLIST_MESSAGE             # the CTA copy
```

`radar.yml` passes the three new secrets (`TELEGRAM_CHANNEL_ID`,
`TELEGRAM_CHANNEL_BOT_TOKEN`, `WAITLIST_URL`); all degrade gracefully if unset.

## Out of scope

- A stored subscriber list / any DM mailing of non-owners (privacy choice).
- An inbound webhook bot — the run stays one-shot.
- Paid-tier / personalized-lesson generation — the waitlist only *validates* demand
  for it (see plan/plan.md, v8 monetization note).
