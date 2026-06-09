# Idea: Minimal multi-user personalization (parked)

> Status: PARKED — revisit after learning-method enrichment (Delftse methode etc.)
> is in place. Validate broadcast engagement first; scale infra only when users
> force it.

## Core insight

The personalization hook already half-exists: `gap_scorer.score()` (radar/gap_scorer.py)
accepts a `profile` dict `{"known": ..., "goals": ...}` and is **pure Python — no LLM
call**. Per-user re-ranking of the day's already-scored skills is essentially free.

## How it works (one sentence)

The daily run stays exactly as-is (one scrape, one global lesson, one broadcast);
after global scoring, re-rank the same day's skill mentions once per user with their
profile and DM each a short "📡 For you" digest — zero extra LLM calls.

## Phase 1 — Profiles + personalized ranking DM (~1 day, ~200-250 lines)

1. **User profiles** — new `storage/profiles.py`

   ```json
   {
     "name": "Anna",
     "telegram_chat_id": "123456789",
     "known": ["react", "typescript"],
     "goals": ["llm agents", "rust"],
     "active": true
   }
   ```

   ⚠️ Privacy: repo is public, chat IDs are PII. Preferred: store all profiles as
   one JSON blob in a GitHub secret `PROFILES_JSON` (fine to ~20-30 users). Later:
   small private repo/gist fetched at runtime.

2. **Personalization step** — new `radar/personalize.py` (~60 lines).
   For each active profile: `gap_scorer.score(mentions, memory, user_profile, history)`
   → top 3 → format a digest from existing fields (`skill`, `evidence`, `sources`).
   No LLM.

3. **Per-user DM** — add `send_personal(chat_id, text)` to `delivery/telegram_sender.py`
   (~15 lines, reuses `_send_message` machinery). Called in `main.py` after delivery,
   each user failure-isolated via the existing `_fail()` / run-report path. Users stay
   in the channel for the full lesson/audio.

4. **Onboarding**: Tally waitlist → manually copy answers into profiles JSON.
   At <50 users, manual is correct.

**Cost at 50 users: $0.** No new LLM tokens, no new infra; Actions runtime +~30s.

## Phase 2 — One light LLM call per user (only if users ask)

Tailor the day's existing grounded brief ("explain this for a React dev") — one short
call per user. 50 users fits NIM's 40 RPM with a simple throttle (~2 min added).

## Phase 3 — Per-user spaced repetition (later)

Per-profile memory mirroring `skill_memory` so each user's taught/known skills sink
in *their* ranking over time.

## Explicitly NOT doing (until ~100+ active personalized users)

No DB, no Celery/Redis, no Oracle VM, no auth dashboard, no per-user audio.
Each becomes worth it only when user count forces it.
