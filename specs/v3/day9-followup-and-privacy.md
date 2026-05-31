# v3 / Day 9 — Perplexity follow-up link + PII redaction

**Goal:** replace the `/recap` Telegram bot with a zero-infrastructure follow-up
path, and stop personally identifiable information (PII) from leaving the
pipeline. Both change *what is sent out*, so they ship together.

## Why replace `/recap`

The day-7 bot (`recap/` + `.github/workflows/recap.yml`) only ran on manual
dispatch (no cron), so it answered nothing unless a run was started by hand. Each
reply was a single LLM call grounded only in `skill_memory.json` summaries — full
briefs were never in scope. A Perplexity deep link instead:

- needs no server, no workflow, no polling — it is just a URL in each lesson;
- loads the **full committed brief** as context, not a summary;
- lets the user keep asking in a real thread, not one-shot Telegram replies.

So `recap/` and `recap.yml` are deleted; the bot's only caller of
`storage.load_brief` is gone, but the helper stays (cheap, still part of the
state API).

## Follow-up link (`delivery/followup.py`)

- `perplexity_url(skill, brief_file) -> str` builds
  `https://www.perplexity.ai/search/new?q=<url-encoded query>`. The query tells
  Perplexity to read the brief's raw URL and answer follow-ups grounded in it.
- The raw URL is `config.BRIEFS_RAW_BASE + "/" + brief_file`. Briefs are named
  `briefs/<YYYYMMDD>-<slug>.md` (see `storage.save_brief`) and committed by the
  radar workflow, so the URL is deterministic.
- `main()` adds `brief_file` to the `lesson` dict so the senders can build the link.
- `telegram_sender` renders it as a `sendAudio` inline-keyboard URL button;
  `email_sender` renders it as an `<a>` button. Both no-op when no brief exists.

**Known caveat:** the link points at the brief's committed raw URL, which resolves
only after the workflow pushes that commit (seconds after the run). It 404s in the
brief window before the push completes; by the time a user taps it, it resolves.

## PII redaction (`radar/privacy.py`)

Collected source text — especially HN "Who is Hiring?" posts — embeds recruiter
emails, phone numbers, and social handles. Those must not reach the LLM, the
committed repo, delivery, or Perplexity.

- `scrub(text) -> str` redacts emails, phone numbers (8+ digits with common
  separators), and `@handles` via regex, leaving technical text (e.g. `Python
  3.12`, `Kubernetes 1.30`) intact.
- Applied in `main._scrape()` to every item's `title`/`text` **at ingestion** —
  before dedup, the LLM, persistence, delivery, and the Perplexity link. One choke
  point covers every downstream sink.
- Regex catches structured PII with high precision; free-text **names** are not
  caught — for those we rely on the extract prompt asking for skills only, plus
  data minimization (only `hn:<id>`-style keys, no source text, are persisted).

## Schedule change

`radar.yml` cron moves from `0 6 * * 1-5` (weekdays) to `0 6 * * *` (every day).
The Stack Overflow agent's week-over-week delta is keyed by ISO week, so it stays
weekly regardless; the other three sources are daily.

## Testing (offline)

- `privacy.scrub`: redacts email/phone/handle; preserves technical text and
  version numbers; empty input is safe.
- Existing delivery tests still pass (button helpers no-op without `brief_file`).

## Acceptance criteria

- [ ] `recap/` and `.github/workflows/recap.yml` removed; no `/recap` references
      remain in code (only historical specs + superseded notes).
- [ ] Each delivered Telegram/email lesson carries a Perplexity follow-up link
      built from the committed brief.
- [ ] PII (emails/phones/handles) is scrubbed at ingestion before any sink.
- [ ] Radar cron runs daily.
- [ ] Offline tests pass; ruff clean.

## Out of scope

- Free-text name redaction (no reliable regex; mitigated by prompt + minimization).
- Server-hosted / real-time follow-up chat.
