# LearnX-Radar — Plan

A self-updating curriculum engine that watches the developer world for emerging
skill gaps and auto-generates personalized audio lessons, delivered daily.

---

## What it is

LearnX-Radar combines two existing systems:

- **Daily-CronJob** — scheduled scraping, summarization, and delivery pipeline
- **LearnX-CLI** — markdown-to-audio-lesson conversion with LLM curriculum and TTS

The result: a cron-driven pipeline that detects rising skills in the real world,
synthesizes a teaching brief, generates a LearnX audio lesson from it, and delivers
it to you every morning before you open your laptop — without a human author.

This is a standalone app. No external platform integration.

---

## LLM Stack

All LLM calls go through the **NVIDIA NIM API** (`build.nvidia.com`).

| Model | Use | Why |
|---|---|---|
| `meta/llama-3.3-70b-instruct` | curriculum planning, dialogue generation, skill extraction, brief writing | capable 70B instruct, fast (~6s/brief) and reliable on the NIM free tier — handles the full pipeline |
| `meta/llama-3.3-70b-instruct` | summarization, Q&A | same model; no need to split by task at this scale |

> **Model change (2026-05-30):** the plan originally specified `z-ai/glm-5.1`,
> but its inference endpoint hangs intermittently on the NIM free tier — even a
> 10-token call timed out at 90s, while every other model on the same key
> responded in under a second. Switched to `meta/llama-3.3-70b-instruct`
> (~6s/brief, reliable). This is exactly the one-constant swap the design
> anticipated; nothing else changed.

**Why NVIDIA NIM over Groq / OpenRouter:**

- **No token billing** — free tier runs on rate limits only (40 RPM), not credits or budgets
- **No exhaustion** — the free tier does not expire or deplete; a daily cron making
  10–20 calls per run is nowhere near the limit
- **OpenAI-compatible API** — swap `base_url` and `model` name, everything else is
  identical to any OpenAI SDK call; easy to maintain
- **Scalable upgrade path** — if volume grows, NVIDIA NIM paid tier starts at
  $0.10/million tokens; no code changes required, just the API key

```python
# llm_config — the only change needed vs Daily-CronJob
BASE_URL = "https://integrate.api.nvidia.com/v1"
MODEL    = "meta/llama-3.3-70b-instruct"
```

**On model choice:** GLM-5.1 was the original pick (flagship MoE, 131K context).
It proved unreliable on the NIM free tier (see model-change note above), so the
canonical model string is now `meta/llama-3.3-70b-instruct`. If GLM-5.1's free
endpoint stabilizes — or on the paid tier — switching back is a one-line change
in `config.py`.

---

## Architecture

```
GitHub Actions (cron 06:00 UTC, every day)
  └── agents/
       ├── github_trending_agent.py    → top repos by language/topic (no auth)
       ├── hn_hiring_agent.py          → "Who is Hiring?" thread keyword extraction
       ├── devto_agent.py              → dev.to RSS top posts by tag
       ├── stackoverflow_agent.py      → SO tags API — frequency delta week-over-week
  └── radar/
       ├── privacy.py                  → redact PII (emails/phones/handles) at ingestion
       ├── skill_extractor.py          → extract skill/tool mentions across all sources
       ├── gap_scorer.py               → score by novelty + frequency + memory coverage
       ├── brief_writer.py             → synthesize a teaching markdown brief from top gap
  └── learnx/
       ├── curriculum.py               → LLM curriculum planner (from LearnX-CLI)
       ├── dialogue.py                 → tutor-student dialogue generator
       ├── audio_builder.py            → TTS via edge-tts (no API key)
  └── delivery/
       ├── telegram_sender.py          → send MP3 + summary to Telegram
       ├── email_sender.py             → daily digest email with lesson preview
       └── followup.py                 → Perplexity deep link seeded with the brief
  └── storage/
       ├── seen_skills.json            → dedup: id→last-seen-date map, expires after 14 days
       └── skill_memory.json           → knowledge state: concepts covered, dates, scores
```

---

## Data Sources

All free, no paid APIs required.

| Source | What it provides | Auth |
|---|---|---|
| GitHub Trending (scrape) | Rising repos by language — proxy for emerging tools | None |
| HN "Who is Hiring?" (Algolia API) | Employer skill demand, real job language | None |
| dev.to RSS | Developer community buzz by tag | None |
| Stack Overflow Tags API | Tag frequency delta — what questions are growing | None |
| Stack Overflow Annual Survey | Baseline skill landscape (static, yearly) | None |
| RemoteOK RSS | Remote job skill mentions | None |

LinkedIn, Indeed, and Glassdoor are excluded — APIs are locked or ToS-restricted.

---

## Build Phases

### v1 — Daily Tech Lesson (foundation)

**Goal:** prove the pipeline end-to-end. One lesson per day, delivered to Telegram.

- Wire Daily-CronJob scraping into a single markdown brief
- Pass brief through LearnX-CLI audio pipeline (GLM-5.1 via NVIDIA NIM)
- Deliver MP3 + 3-sentence summary via Telegram bot and email
- Storage: `seen_skills.json` for dedup (same pattern as Daily-CronJob `seen.json`)

**Output:** a working cron that wakes up, finds something interesting, and teaches it.

---

### v2 — Adaptive Learning Streaks (knowledge state)

**Goal:** stop re-teaching things already covered; build on prior lessons.

- Add `skill_memory.json` — tracks skills covered, dates, Q&A depth, spaced-repetition score
- `gap_scorer.py` weights novelty against memory: a skill seen in the world but absent
  from memory scores highest
- Lesson briefs reference prior context: "Last week we covered async I/O — today's
  lesson connects that to Kafka consumer groups"
- Difficulty auto-scales: beginner on first encounter, intermediate on second, advanced
  on third
- Follow-up Q&A: each lesson links to a Perplexity thread pre-loaded with the committed
  brief (replaced the original `/recap` Telegram bot — see the v2 day-7 spec's
  superseded note and `specs/v3/day9-followup-and-privacy.md`)

**Output:** lessons that feel like a coherent curriculum, not random daily trivia.

---

### v3 — Skill Gap Dashboard (visibility)

**Goal:** make the radar visible. See what the world is demanding, what you've learned,
and what gaps remain — in one place.

- Static HTML dashboard generated daily alongside the audio lesson
- Published to GitHub Pages automatically via the Actions workflow
- Shows:
  - **Trending skills this week** — ranked by source frequency and novelty score
  - **Your coverage map** — skills from `skill_memory.json` plotted against trending ones
  - **Gap highlights** — skills appearing in multiple sources but not yet taught
  - **Lesson archive** — all past lessons with title, date, skill tag, and audio player
- No backend required — everything rendered from `skill_memory.json` and lesson metadata
  at build time

**Output:** a personal skill radar you can open in a browser and share as a portfolio signal.

---

### v4 — Personal tutor (relevance, retention, reach)

**Goal:** turn the global, one-way, unverified radar into a tutor that adapts to
*you*, helps you *retain* what it teaches, and *reaches* you wherever you listen.
The radar is already a strong broadcasting pipeline; v4 makes it personal without
breaking the free-tier, one-shot-cron, no-inbound-server discipline.

Four slices, each a self-contained spec (`specs/v4/`):

1. **Personalization (`day10-personalization.md`)** — scoring gains a sense of
   *me*. New `config.py` constants `KNOWN_SKILLS`, `LEARNING_GOALS` (+ a
   `GOAL_BOOST`) feed `gap_scorer.score()` as extra multipliers: known skills sink
   like table-stakes (you already have them), goal-relevant skills rise. Today the
   only "what does the user know" signal is the *global* `TABLE_STAKES_SKILLS`,
   identical for everyone — this generalizes it to a personal profile. Lives in
   `config.py` alongside `SOURCE_WEIGHTS`, so no new file or dependency.

2. **Actionable briefs (`day11-actionable-briefs-and-quiz.md`)** — the brief gains a
   **"Do this in 5 minutes"** section: one concrete exercise, a code snippet, one
   repo/doc to skim. Fixes the all-prose, nothing-to-do briefs the current prompt
   produces. A `radar/prompts/brief.txt` change plus the dialogue/audio carrying it
   through to the outro.

3. **Recall quiz via Perplexity (`day11` companion)** — a *second*, additive
   Perplexity deep link `quiz_url()` that asks Perplexity to run a short
   active-recall quiz (open-ended, one question at a time, graded against the
   brief). The existing "Ask follow-ups" link is **unchanged**. The quiz targets the
   *previous* lesson's brief (genuine spaced retrieval); it no-ops on day one. Zero
   new infrastructure — it is just another URL button. The auto-persisting
   `getUpdates` mastery loop is noted as a future upgrade, explicitly out of scope.

4. **Podcast feed (`day12-podcast-feed.md`)** — emit a static `podcast.xml` (served
   by the existing Pages workflow) whose `<enclosure>`s point at the daily MP3
   hosted as a **GitHub Release asset**. Releases keep audio out of git history
   (no repo bloat), give a stable URL, and need no new credentials (the workflow's
   `GITHUB_TOKEN` suffices) — unlike Pages (1 GB cap) or committing into the repo
   (unbounded history growth) or GCS (needs a billing account + key). The daily
   lesson lands in a real podcast app for the commute.

**Output:** a daily lesson that is about *your* trajectory, ends with something to
*do*, lets you *test* yourself, and arrives in your podcast app — not just a feed
that talks at you.

> **What v4 deliberately does NOT add:** a skill knowledge-graph, multi-source RAG,
> RLHF, or a continuous/webhook bot. Time-based spaced repetition plus the profile
> already give adaptive scheduling; the rest is complexity without a problem to
> solve yet. The auto-grading inbound loop (daily `getUpdates` poll) is the one
> future piece worth designing carefully, and is held back to its own later spec.

---

## Repo Structure

```
LearnX-Radar/
  agents/                  # data collection (from Daily-CronJob pattern)
  radar/                   # skill extraction, gap scoring, brief writing
  learnx/                  # audio pipeline (from LearnX-CLI)
  delivery/                # Telegram, email
  storage/                 # seen_skills.json, skill_memory.json
  dashboard/               # static site generator (v3)
  specs/                   # day-by-day specs (written before code, LearnX-CLI style)
  plan/                    # this file and future phase plans
  .github/workflows/       # cron job + CI + GitHub Pages deploy
  config.py                # sources, limits, topic filters
  main.py                  # entry point
  requirements.txt
  .env.example             # NVIDIA_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                           # GMAIL_APP_PASSWORD, EMAIL_FROM, EMAIL_TO
  README.md
```

---

## Key Design Decisions

**Spec-driven development** — same discipline as LearnX-CLI. Every feature gets a written
spec before a line of code. Specs live in `specs/v1/`, `specs/v2/`, `specs/v3/`.

**Single LLM provider, single model** — NVIDIA NIM (`meta/llama-3.3-70b-instruct`)
handles every LLM task in the pipeline. No provider-switching logic, no fallback
complexity. If the model name changes (as GLM-5.1 → llama-3.3-70b already showed can
happen), one constant in `config.py` fixes it.

**No paid APIs in the critical path** — the pipeline must run on the GitHub Actions
free tier indefinitely. TTS: edge-tts (no key). LLM: NVIDIA NIM free tier (40 RPM,
no billing). Delivery: Telegram + Gmail (free).

**Standalone first** — no external platform dependencies. The app delivers value
entirely through Telegram, email, and a GitHub Pages dashboard.

**Dedup at two levels** — `seen_skills.json` prevents re-processing the same source item,
but only for a window (`SEEN_TTL_DAYS`, 14): the trend sources use time-stable IDs
(`gh:owner/repo`, `so:tag:week`), so a permanent seen-set would suppress them forever and
collapse the ranking to dev.to-only — the window lets a still-trending item re-surface.
`skill_memory.json` (spaced-repetition novelty) prevents re-teaching a concept too soon.
These are separate concerns: the window can be short because novelty, not dedup, is what
stops a skill being re-taught.

**PII redaction at ingestion** — collected source text (especially HN job posts) can
carry contact PII. `radar/privacy.py` scrubs emails, phone numbers, and `@handles` in
`main._scrape()`, before anything is deduped, sent to the LLM, persisted, delivered, or
linked to Perplexity. One choke point keeps PII out of every downstream sink.

---

## What success looks like

- v1: A lesson MP3 arrives in Telegram every morning. It teaches something real that
  appeared in the developer world in the last 24 hours.
- v2: After 30 days, the lessons feel like a coherent curriculum — they build on each
  other and increase in depth.
- v3: A public GitHub Pages dashboard shows a personal skill coverage map against
  what the developer job market is currently demanding.
- v4: Lessons skip what you already know, lean toward your stated goals, end with a
  5-minute action, offer a one-tap recall quiz, and arrive in your podcast app.