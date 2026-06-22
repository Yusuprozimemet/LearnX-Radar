# v10 / Day 39 — Multi-user Dutch personalization, Phase 1 (let ~5 known people each get their own spaced repetition + a personal cross-day review, sharing one generated lesson)

**Goal:** the Dutch track has always been single-learner — one `dutch_memory.json`,
recall accepted from the owner chat only, one lesson personalized to the owner and
broadcast to everyone else. Let a small, **known** group (~5 people) each keep their
**own** spaced-repetition schedule and a **personal cross-day review**, without
per-user LLM/TTS cost and without accounts, auth, or a backend.

The load-bearing idea: separate **generation** from **selection**. Generation
(writing sentences, rendering audio) stays **global** — one lesson per day, shared
by everyone, so cost is flat in user count. Only **selection** — which of the words
each learner owes is due today — is per-user, and that's a cheap query over each
learner's own state. Spaced repetition is already the mistake-driven engine
([[day33-recall-feedback]]); making the memory file per-user makes the whole loop
per-user for free. This is **Phase 1** of [plan/personalization.md](../../plan/personalization.md);
Phase 1.5 (batched mistake-driven generation) and Phase 2 (self-serve
subscribe/unsubscribe/delete + GDPR) are deliberately deferred.

Built on [[day38-private-state-repo-and-llm-resilience]]: per-user files (and the
chat ids that name them) live in the **private** state repo, which removed the old
"chat IDs as PII in a public repo" objection.

Everything is gated behind `ALLOWED_CHAT_IDS` — empty means single-user, byte-for-byte
unchanged, and all prior tests pass untouched.

---

## 1. Allowlist + per-user state (config.py, storage/state.py)

- `ALLOWED_CHAT_IDS` (comma-separated env) names the learners; `config.dutch_user_chat_ids()`
  returns the owner first, then the allowlist, de-duped. `dutch_multiuser_active()`
  is true only when more than the owner is configured.
- `load_dutch_memory(chat_id)` / `save_dutch_memory(memory, chat_id)`: the **owner**
  (or `chat_id=None`) keeps the historical unsuffixed `dutch_memory.json` — no
  migration, still monkeypatchable in tests — while every other learner gets
  `dutch_memory_<chatid>.json` beside it in `STATE_DIR`.
- `review_token(chat_id)`: an HMAC of the chat id under `REVIEW_TOKEN_SECRET` (falls
  back to the bot token). Names the published `review/<token>.json` so it isn't
  enumerable by raw chat id — *public-with-a-password*, acceptable because the
  contents (which words are due) are low-stakes.

## 2. Per-user recall + review reports (delivery/telegram_recall.py)

One `getUpdates` batch already carries every learner's deep-link taps, keyed by
sender. `fetch_inbound` now also returns, alongside the unchanged owner-only
`recall`/`ratings`:

- `recall_by_user` — `dr_<YYMMDD>_<marks>` from any allowlisted sender (the existing
  trainer "Save results" loop, now per-user).
- `review_by_user` — a new `rv_<YYMMDD>_<marks>` payload: a personal **review** report,
  marks positional over the review list published for that date.

`main._ingest_dutch_multiuser` folds each learner's recall + review into **their**
file; `record_dutch_review` applies the same right/wrong logic as `record_dutch_recall`
(a failed word resets `reps` and is pulled forward), maps positions back to ids via
the stored `last_review` order, and is idempotent (a duplicate tap is a no-op).

## 3. Cross-day review build + publish (dutch/review.py)

After today's shared lesson is recorded into **every** learner's SR file
(`main._persist_dutch_multiuser`), `review.build` distills each learner's due words
(`dutch_due_words`) and pairs each with a real example sentence + audio span pulled
from the day it was taught — indexed from the **lessons/ archive** segments. Pure
composition + file reads, no LLM. The result, `review/<token>.json` (canonical
"what's due"), plus `memory["last_review"] = {date, ids}` so an `rv_` report's
positions map back. Today's new words aren't due yet, so the review is genuinely the
words each learner still owes across all past days. `pages.yml` copies `review/`
to the site.

## 4. Delivery fan-out (delivery/telegram_sender.py)

`_targets()` includes the allowlist when multi-user is active, so each learner
receives the (shared) lesson DMs. Each learner's Dutch trainer button carries their
own `?u=<token>`; the channel and non-learners get the plain trainer URL. Rating
buttons stay owner-only.

## 5. Trainer page — the `herhaling` tab (dashboard/dutch.html)

A fourth tab that appears **only** when the page is opened with `?u=<token>`. It
fetches `review/<token>.json`, drills each due word from memory (blanking the word
out of its archived sentence, or a gloss-only prompt), and plays the cross-day audio
span from each word's own day MP3 (a second `<audio>` element; cross-origin media
load needs no CORS, and the release CDN honours Range). The published JSON is
**canonical**; localStorage only caches today's attempts. "Herhaling opslaan" builds
the `rv_` deep link (bot username read from the lesson's `report.bot`).

## 6. The shared lesson is unchanged (by decision)

New-word selection, the mistake-driven coach ([[day36-mistake-driven-dutch-coach]]),
and the backlog pause ([[day37-backlog-backpressure]]) still run off the **owner's**
state and shape the one shared lesson; the other learners ride along on it, and their
personalization lives entirely in the review tab. Decoupling the shared lesson from
the owner is a later phase.

---

## 7. Tests

- `dutch/tests/test_review.py` (new): `review.build` distills only due words, attaches
  the archived sentence + audio span, falls back to gloss-only with no example, caps
  at `max_items`, skips ids gone from the bank.
- `storage/tests/test_state.py`: per-user file routing (owner unsuffixed, others
  suffixed), `review_token` stability/uniqueness, `save_review`, and
  `record_dutch_review` (positional, idempotent, rejects a mismatched date).
- `delivery/tests/test_delivery.py`: `fetch_inbound` routes recall/review per sender
  and ignores non-allowlisted chats; the trainer markup carries `?u=<token>`.
- Existing suite unchanged: with `ALLOWED_CHAT_IDS` empty the single-user paths are
  byte-identical, so all prior tests pass.