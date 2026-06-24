# v11 / Day 40 — Monitoring: a Status tab for pipeline health and learner progress (turn the same-day failure DM into a visible track record, and aggregate the cohort's Dutch learning)

**Goal:** the daily run already *captures* health signals and *writes* per-learner
recall state, but both are nearly invisible. Stage failures are DM'd once and
forgotten ([main.py](../../main.py) `_report`); the NVIDIA→Groq circuit breaker
trips silently in logs; each learner's Dutch recall lives in their own
`dutch_memory_<chatid>.json` but is never aggregated. Add a third dashboard tab
**📊 Status** with two views, both built the zero-backend way (commit JSON to the
private state repo each run, render static HTML / fetch token-gated JSON on Pages):

1. **Ops health** — is the machine running well (run history, stage heatmap, LLM
   fallback frequency, per-source item counts).
2. **Learning** — the owner's own progression (always) plus a **cohort** view that
   aggregates the known multi-user group's recall, active now that
   `ALLOWED_CHAT_IDS` is populated ([[day39-multiuser-dutch-personalization]]).

This pairs with [[day38-private-state-repo-and-llm-resilience]] in spirit:
guarded, config-driven observability that never touches pipeline correctness.

---

## 1. Run history (`run_history.json`, private state)

[main.py](../../main.py) already tracks stage outcomes via `_fail()` into
`_failures`. Promote that to a structured per-run record and persist it.

- New module `storage/run_history.py` (pure where possible): `record_run(...)`
  builds one entry — `{date, started, duration_s, stages: {name: "ok"|"fail"},
  llm: {breaker_tripped, nvidia_timeouts, served_by_fallback}, sources: {name:
  count}, delivery: {telegram, channel, email}}` — and `append(entry,
  max_days=60)` writes a rolling list (capped like `trending_history`).
- main.py records each stage's outcome as it runs (success path too, not only the
  `_fail` path) and the per-source counts already printed in `_scrape`. It writes
  the entry in the `finally` of `main()`, next to `_report()`, so a crashed run is
  still recorded (with the failing stage marked).
- **No raw exception text is persisted** — only stage name + `ok|fail`. Exception
  detail stays in the owner DM (`_report`) and Actions logs. This keeps the file
  safe to render on the **public** dashboard.
- [learnx/llm.py](../../learnx/llm.py) exposes a `breaker_state()` getter
  (`{tripped, timeouts}`) reading the existing process-global `_nvidia_tripped` /
  `_nvidia_timeouts`, so the run record can report fallback behaviour.

## 2. Cohort learning aggregate (`cohort/<owner-token>.json`, token-gated)

[main.py](../../main.py) `_persist_dutch_multiuser` already loops every
`config.dutch_user_chat_ids()` and loads each learner's `dutch_memory`. Collect
those memories and feed a new **pure** aggregator.

- New module `dutch/cohort.py`: `build_cohort(memories: list[dict]) -> dict` →
  `{learners_total, active_7d, active_30d, cohort_recall_30d, cefr_distribution,
  hardest_words: [{word, fails, learners_failing}], daily_recall: [{date, right,
  wrong}]}`. Reuses the recall-rate and most-failed logic shape already in
  [dashboard/builder.py](../../dashboard/builder.py) (`_recall_rate_html`,
  most-failed table) — anonymous aggregates only, **no chat id or token in the
  output**.
- Persisted under the **owner's** review token (`cohort/<review_token(owner)>.json`)
  so it rides the same `?u=<token>` gating as `progress/` and `review/` — the
  cohort summary is owner-only, fetched client-side, never a guessable public file.
- Single-user (no allowlist) → cohort has one member (the owner); the view still
  renders, just `learners_total = 1`.

## 3. Status tab (dashboard)

Add a third tab to [dashboard/builder.py](../../dashboard/builder.py) `_tabs`
(`📊 Status`, alongside 📡 Radar / 🇳🇱 Dutch).

- **Ops health** — rendered **server-side** from `run_history.json` into the
  public page: last-run time + ✅/❌, a 30-day stage heatmap (one column per run,
  one row per stage), LLM fallback frequency, a 7-source health row (any source at
  0 items flagged). Safe because §1 persists no raw error text.
- **Learning** — the owner's own progression (streak history, CEFR toward B1,
  30-day recall) always; the **cohort** block fetched **client-side** from
  `cohort/<token>.json` only when the page is opened with `?u=<token>` (same
  pattern as the LESSEN scorecard in [dutch.html](../../dashboard/dutch.html)).
  Without a token the Learning view shows only the public owner aggregate.
- `dashboard/__main__.py` reads `run_history.json`; the Pages deploy copies
  `cohort/` to the published tree like it copies `progress/`.

## 4. Activate multi-user

Set the GitHub repo secrets so the cohort view has real data:

- `ALLOWED_CHAT_IDS` — comma-separated Telegram chat ids of the consented group
  (each must have `/start`-ed the bot first; owner is auto-included).
- `REVIEW_TOKEN_SECRET` — stable HMAC key (already falls back to the bot token;
  set explicitly so tokens survive a bot-token rotation).

No code change — `dutch_multiuser_active()` flips on once `ALLOWED_CHAT_IDS` is
non-empty.

## 5. Tests

- `storage/tests/test_run_history.py`: `record_run` shape; `append` caps at
  `max_days` and preserves order; a fail-marked entry round-trips.
- `dutch/tests/test_cohort.py`: `build_cohort` aggregates recall across several
  memories, computes CEFR distribution + hardest words, contains **no** chat
  id/token, and handles the single-member case.
- `dashboard/tests/test_builder.py`: the Status tab renders with `run_history`
  present and degrades to an empty-state when absent.
- `learnx/tests/test_llm.py`: `breaker_state()` reflects trips/timeouts.

## 6. Limitation (by design)

This monitors the **known, consented** audience only. Anonymous `dutch.html`
visitors keep their progress in `localStorage` — it never reaches the server, so
their learning is **not** observable here, by design. Channel/Spotify listeners
expose only membership (held by those platforms), not learning. Aggregate traffic
for the anonymous audience would require opt-in analytics — tracked separately as
the parked "listener analytics" follow-up, not part of this slice.