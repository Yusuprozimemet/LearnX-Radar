# v9 / Day 33 — Recall feedback into spaced repetition (learning efficiency loop)

**Goal:** the Dutch spaced-repetition scheduler widens a word's interval every
time the word is *shown* — exposure, not learning. The Delft trainer (Day 32)
measures actual recall (which blanks were right). Close the loop: recall results
flow back into `dutch_memory`, so failed words return sooner and recalled words
space out further. Scheduling driven by what you can produce, not what you were
sent.

---

## 1. Getting results back without a server

The pipeline is a daily cron with no inbound endpoint — but it already owns a
Telegram bot, and Telegram retains messages for `getUpdates`. So the browser
reports *to the bot*:

- The trainer page's "✅ Save results" button opens a deep link:
  `https://t.me/<bot>?start=dr_<base64 payload>` — one tap sends the payload as a
  `/start` message from the learner's own Telegram account.
- Payload: lesson date + per-word-id right/wrong, e.g. `2026-06-09:afspraak=1,beginnen=0`,
  base64url-encoded (Telegram caps `start` payloads at 64 chars — at 4–10 words
  a day with short ids this fits; ids are truncated/hashed if needed).
- Next morning's run calls `getUpdates`, filters `/start dr_*` messages from
  `TELEGRAM_CHAT_ID` (owner-only for now — this is the personal learning loop),
  decodes, and acknowledges by advancing the update offset.

No new infra, no webhook, no token in the browser: the page only builds a URL.

## 2. Folding recall into the scheduler (`dutch/wordlist.py` + storage)

Per reported word:

- **right** → behave as today (rep count up, interval widens).
- **wrong** → rep count resets to 1 → the word reappears at the base interval
  (tomorrow), exactly like a forgotten card in any SR system.
- **unreported** (lesson never trained) → unchanged — exposure-based scheduling
  remains the fallback, so skipping the trainer never punishes.

`dutch_memory` words gain `recall_right` / `recall_wrong` counters — the raw
material for a per-word mastery view.

## 3. Monitoring surface

The dashboard's Dutch tab gains two numbers it currently can't know: **recall
rate** (right / reported, rolling 30 days) and **struggling words** (most-failed,
shortest-interval). This is the difference between "the streak is alive" and
"it's working".

---

## Out of scope

- Multi-user results (owner-only; generalizing waits for the personalization
  track — see `ideas/personalization-multiuser.md`).
- Webhooks / hosted endpoints (getUpdates polling on the daily run is enough).
- Grading partial/typo answers (right/wrong as the trainer judged them).
- CEFR auto-advancement changes (recall data may inform it later, separately).
