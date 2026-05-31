# v2 / Day 7 — `/recap` Telegram Q&A bot

> **SUPERSEDED (2026-05-31).** This bot was removed. Follow-up Q&A is now a
> Perplexity deep link seeded with the committed brief — see
> [`specs/v3/day9-followup-and-privacy.md`](../v3/day9-followup-and-privacy.md).
> Reasons: the polling workflow only answered after a manual dispatch (no cron),
> replies were a single ungrounded LLM call capped at summaries, and a deep link
> needs zero infrastructure while giving the user full, continuable Q&A over the
> whole brief. The spec below is kept as a record of the original design.

**Goal:** ask the bot about past lessons from Telegram. Send `/recap <question>`
and get an answer grounded in your learning history (`skill_memory.json`).

## Architecture: scheduled polling (no server)

The daily pipeline is a one-shot cron; a chat bot needs to *receive* messages.
To stay server-free and free-tier-forever, **a scheduled GitHub Actions workflow
polls Telegram every ~15 min**, answers any pending `/recap` commands, and exits.

- Telegram `getUpdates` returns unconfirmed updates; calling it again with
  `offset = last_update_id + 1` confirms them server-side, so the next run won't
  re-see them. **No local offset/state file needed** — Telegram tracks it.
- Replies aren't instant (≤ ~15 min delay). Fine for "recap my lessons"; this
  isn't live chat. (Public repo → Actions minutes are free.)
- **Security:** only messages from `config.TELEGRAM_CHAT_ID` are answered;
  everything else is ignored, so the bot won't talk to strangers.
- `getUpdates` only works when no webhook is set (we don't set one). ✓

## Components (`recap/`)

```
recap/__init__.py
recap/bot.py        poll cycle: fetch → handle /recap → reply → confirm offset
recap/__main__.py   `python -m recap` runs one cycle (what the workflow calls)
recap/prompts/recap.txt
recap/tests/
```

`bot.py` functions (small, testable; I/O separated from logic):
- `fetch_updates() -> list[dict]` — `getUpdates`, return messages.
- `recap_questions(updates) -> list[(update_id, question)]` — keep only messages
  from our chat whose text starts with `/recap`; strip the command to the question.
- `answer(question, memory, chat_fn=chat) -> str` — one LLM call grounded in a
  catalog built from memory.
- `send_message(text)` / `confirm(offset)` — Telegram I/O.
- `poll(chat_fn=chat)` — orchestrates one cycle; confirms the offset at the end
  even if a reply fails, so a bad question can't wedge the queue.

## Grounding (see decision)

The Q&A catalog is built from `skill_memory.json`: per skill — name, times
taught, last date, difficulty, and the one-line `summary`. The LLM answers from
that catalog ("what have I learned about X?", "recap Kafka", "what should I
review?"). If a topic isn't in the catalog, it says so rather than inventing.

`/recap` with no question → a short usage hint + the list of skills learned.

## Workflow

`.github/workflows/recap.yml`: `schedule` (every 15 min) + `workflow_dispatch`,
runs `python -m recap` with `NVIDIA_API_KEY` + `TELEGRAM_*` secrets (already set).
No state commit — Telegram tracks the offset.

## Testing (offline)

- `recap_questions`: filters foreign chat ids, non-`/recap` text; strips command.
- `answer`: canned `chat_fn` + synthetic memory → catalog includes skills; empty
  memory → graceful "nothing learned yet".
- `poll`: monkeypatch fetch/send/confirm → confirms offset even when a reply
  raises; ignores messages from other chats.
- catalog builder formatting.

## Acceptance criteria

- [ ] `python -m recap` runs one cycle: reads updates, answers `/recap` from our
      chat, replies, confirms offset. No crash on no updates.
- [ ] Only the configured chat is answered.
- [ ] Answers are grounded in real lesson history; unknown topics handled.
- [ ] Offline tests pass; ruff clean.
- [ ] Live: send `/recap what have I learned?` → get a sensible reply within a
      poll cycle.

## Out of scope

- Real-time replies / webhook hosting. Deep Q&A over full brief text (catalog
  uses summaries; full briefs aren't persisted).
