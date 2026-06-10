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

### v5 — Dutch coach (a second learning track)

**Goal:** the same daily engine that teaches you an emerging dev skill also helps
you learn **Dutch** (A2, with room to grow). It rides the existing run — same LLM,
same edge-tts, same Telegram/email/podcast delivery, same spaced-repetition idea
and dashboard — so it adds a *domain*, not a parallel app. No new credentials or
services.

The defining choice: **vocabulary is anchored to a curated, pre-verified word
list** (`dutch/wordlist.json`), so the words you learn are always correct. The LLM
only writes example sentences and a short dialogue *around* a fixed set of words —
it never invents vocabulary. This sidesteps the one real risk of an LLM teaching a
language (plausible-but-wrong words/genders).

Three slices, each a self-contained spec (`specs/v5/`):

1. **Foundation (`day16-dutch-foundation.md`)** — `dutch/` module + the curated
   A2 word bank. Each morning it picks a small themed word set (themes
   **alternate** day-to-day: everyday/survival Dutch vs. tech-flavored Dutch tied
   to the day's dev topic) and makes one LLM call to wrap those exact words in A2
   example sentences + a short dialogue. A 🇳🇱 section is appended to the existing
   email and sent as a Telegram message. No memory yet.

2. **Audio + spaced repetition + quiz (`day17-dutch-audio-srs-quiz.md`)** —
   `storage/dutch_memory.json` (mirrors `skill_memory.json`) tracks every word with
   spaced-repetition due dates, so each day mixes *new* words with the words *due
   for review*; it also tracks a CEFR level and a streak. The Dutch dialogue is
   rendered to a second MP3 via edge-tts **Dutch voices** (slower rate for A2),
   delivered alongside the dev lesson and carried into the podcast feed. A Dutch
   `quiz_url()` (same Perplexity deep-link pattern) quizzes you on *yesterday's*
   words — genuine spaced retrieval.

3. **Dashboard Dutch tab (`day18-dutch-dashboard-tab.md`)** — the static page
   gains a top **nav toggle** between **Radar** and **Dutch** (vanilla DOM-swap,
   same technique as the date picker). The Dutch tab shows progress (streak, CEFR,
   words learned), the count due for review, recent words, and a Dutch lesson
   archive with an inline audio player. Built from committed state alone
   (`dutch_memory.json`), so the keyless Pages workflow renders it like everything
   else.

**Output:** every morning you get a dev lesson *and* a Dutch lesson — words you can
read, hear, review on a spaced schedule, and self-test — across email, Telegram,
and your podcast app, with both tracks visible on one dashboard.

> **What v5 deliberately does NOT add:** an LLM that invents Dutch vocabulary
> (the curated list is the guardrail), speech recognition, or any
> inbound/answer-checking server. Grammar, reading, and KNM are the next track
> (v6); retention in v5 comes from spaced repetition + the self-directed Perplexity
> quiz, consistent with the rest of the project's one-shot-cron, no-inbound
> discipline.

---

### v6 — Inburgering B1 track (the language skills + KNM)

**Goal:** turn the v5 vocab+listening coach into a **systematic path toward the
inburgering B1 exam**. v5 covers ~2 of the 6 exam parts (listening, and reading in
passing); v6 adds the rest in stages, with a measurable monthly sense of progress.
Target level is **B1** (the standard learning route); pace is **adaptive** (starts
gentle, ramps with streak + review accuracy).

> **Scope honesty:** this app is a daily *supplement*, not a replacement for a
> course or DUO's official practice exams (*oefenexamens*). It keeps you practising
> every day and measures progress; the official prep and a teacher remain the
> backbone for a high-stakes exam.

**Two enabling changes carried from v5:**

- **B1 word bank.** The A2 seed (`dutch/wordlist.json`, ~112 words) grows toward the
  B1 range (~2,500–3,200) in reviewed batches via `dutch/build_wordlist.py` — a data
  effort, generated-then-frozen, never a runtime LLM call (the v5 guardrail holds).
- **Adaptive pacing.** `DUTCH_NEW_WORDS_PER_DAY` becomes a function of streak +
  recent review accuracy (≈5/day → ≈12/day), with a CEFR auto-advance A2→B1 as
  mastery accrues. This refines the v5 day-17 selection rather than replacing it.

**The skill slices (each its own spec in `specs/v6/`):**

1. **KNM — Knowledge of Dutch Society.** One bite-sized fact + a question each
   morning, cycling the official KNM themes (work & income, health & care, housing,
   education, politics & constitution, history, geography…). Self-contained, grounded
   in a curated KNM fact bank (same "frozen, reviewed data" discipline as the word
   list, so facts can't be hallucinated), delivered in the 🇳🇱 block and tracked on
   the Dutch dashboard tab. A whole exam part with low build cost — the chosen
   *first* addition.

2. **Reading — comprehensible input.** A short daily text that scales A2→B1, built
   mostly from words already in memory plus a few new ones (i+1), with an English
   gloss and 1–2 comprehension questions. Consolidates vocabulary far faster than
   isolated words and directly rehearses the *Lezen* exam skill.

3. **Grammar — weekly focus, practised in context.** A rotating weekly grammar point
   (word order/V2, perfect & imperfect tense, separable verbs, `omdat/want`,
   relative `die/dat`, `om…te`, comparatives…) woven into that week's sentences,
   dialogue, and reading — grammar *used*, not drilled cold. A small curated grammar
   syllabus drives the rotation; the LLM applies it, never defines it.

**Output:** a daily lesson that now exercises listening, reading, vocabulary,
grammar, and Dutch-society knowledge — a coherent B1/inburgering curriculum you feel
improving month over month.

> **Held for a later track:** active *production* — daily writing prompts
> (*Schrijven*) and speaking/shadowing exercises (*Spreken*) — plus **monthly scored
> mock exams** mapping to the six exam parts. These are where self-checking is
> hardest (no inbound channel), so they get their own careful design. The roadmap
> still names them so the v6 data model (mastery %, per-skill tracking) is built to
> accommodate them.

---

### v7 — Accuracy & grounding (teach the *right* thing, *grounded*)

**Goal:** raise the quality of *what* the radar picks and *how grounded* each lesson
is, without leaving the free-tier, one-shot-cron discipline. The earlier phases
proved the loop; v7 sharpens its judgement. Four slices, each a self-contained spec
(`specs/v7/`) behind a config rollback flag.

1. **Discovery sources (`day23-discovery-sources.md`)** — widen input from **4 to 7
   sources** by adding three *open-vocabulary* feeds (Reddit `.rss`, the HN front
   page, Lobste.rs), so the radar can surface a skill it was never pre-configured to
   watch — not just track a fixed tag/language list. All zero-auth and stateless.
   Per-source weights (`SOURCE_WEIGHTS`) keep real job-market demand above buzz.

2. **Grounded briefs (`day24-brief-grounding.md`)** — instead of writing the brief
   from the skill *name* alone, read the **actual source text** that surfaced the
   skill (keyless Jina reader) plus fresh Exa web results (`EXA_API_KEY`), and cite a
   real `## Sources` list **authored in code** (the LLM never writes URLs — it
   fabricates them). Grounding helpers are vendored from the sibling LearnX-Search
   into `radar/research/`. Read budget chosen by experiment (`scripts/exp_grounding.py`).

3. **Map-reduce extraction (`day25-mapreduce-extraction.md`)** — replace the
   single-pass extractor (which capped recall and rested the demand weight on the LLM
   tallying sources) with **map** (chunk the corpus → extract candidates per chunk for
   recall) → **reduce** (merge variants via `SKILL_ALIASES`) → **attribute** (compute
   each skill's source set by *scanning the corpus*, deterministically). Chunk size
   chosen by experiment (`scripts/exp_extraction.py`).

4. **Cross-day momentum (`day26-momentum-and-vectordb.md`)** — fold a **momentum
   multiplier** into scoring: look back over `trending_history` (matched by canonical
   name) and boost skills *sustained and accelerating* across days while damping
   one-day spikes. Orthogonal to the spaced-repetition novelty signal (that's "have
   *we* taught it"; momentum is "is the *world* rising"). A vector-DB phase (3b) is
   named but gated as optional.

**Output:** the daily topic is more often a skill genuinely rising in the world, and
the brief that teaches it is grounded in and cites real sources rather than the
model's priors.

---

### v8 — Reach & distribution (get the lesson to people)

**Goal:** the pipeline is a strong daily *author*; v8 turns it into a small *product*
with real distribution — still no inbound server, no stored subscriber PII, no paid
tier. This is the top of a funnel toward the personalized (paid) lessons the waitlist
validates. The slices live in `specs/v8/`.

1. **Public distribution (`day27-public-distribution.md`)** — three things, each
   config-flagged and failure-isolated:
   - **Channel broadcast.** `telegram_sender.send()` fans the lesson out to the owner
     DM *and* an optional public channel (`TELEGRAM_CHANNEL_ID`, e.g. `@learnradar`),
     posted by a *separate* public bot (`TELEGRAM_CHANNEL_BOT_TOKEN`) so the public
     product is decoupled from the personal DM/quiz bot. **Telegram holds the member
     list, so no subscriber PII is ever stored** — the GDPR-clean model chosen over a
     repo-stored subscriber list.
   - **Full-lesson PDF.** `delivery/pdf.py` renders the brief to a PDF via `xhtml2pdf`
     and attaches it (`sendDocument`), so subscribers get the complete formatted lesson
     — audio captions cap at 1024 chars, which truncated the Dutch dialogue.
   - **Weekly waitlist CTA.** `post_waitlist()` posts a personalization early-access
     call-to-action to the channel on its configured weekday, linking a hosted form
     (Tally, `WAITLIST_URL`) — we store nothing.

2. **Reach & discoverability (`day28-reach-and-discoverability.md`)** — three
   additive, no-PII reach levers:
   - **Weekly dev.to cross-post.** `delivery/devto_publisher.py` cross-posts the lesson
     brief to dev.to via the Forem API (`DEVTO_API_KEY`) — *weekly*, **draft by
     default** for review, with a footer linking back to the channel. SEO + a second
     audience; degrades to a no-op without a key.
   - **Apple/Spotify-compliant podcast feed.** Extend `dashboard/feed.py` with the
     iTunes directory tags, an owner email for ownership verification, and square cover
     art (`cover.png`); de-duplicate episodes by audio GUID so a re-run never doubles
     an episode. The show then lists in Spotify and Apple Podcasts, not just generic
     RSS apps.
   - **Social preview.** The dashboard gains Open Graph / Twitter card tags
     (`og.png`) and a "Join on Telegram" CTA so a shared link renders a rich card.

3. **Run failure report (`day29-run-report.md`)** — observability for the unattended
   cron. The per-stage guards keep the run alive but bury failures in Actions logs;
   now `main()` collects every guarded failure (source fetch, audio, delivery,
   persistence — including per-target Telegram failures that `send()` previously
   swallowed) and DMs a summary to the **owner chat only** at the end of the run
   (`RUN_REPORT_ENABLED`), so a dying channel is a same-day ping, not a
   weeks-later surprise.

**Output:** the same daily lesson now reaches people on Telegram, Spotify, Apple
Podcasts, dev.to, and the web — with a waitlist capturing demand for the personalized
tier — all on the free tier, storing no subscriber data, and with stage failures
DM'd to the owner the same day.

> **Monetization direction:** the free channel is top-of-funnel for a paid
> *personalized* tier (lessons matched to a learner's stack & goals, with a real
> mastery loop). The honest read is that **B2B / L&D** is likely a stronger wedge than
> B2C; the waitlist exists to **validate willingness-to-pay before** building paid
> infrastructure and any private datastore.

---

## Repo Structure

```
LearnX-Radar/
  agents/                  # data collection — 7 open-vocab sources (v7 Day 23)
  radar/                   # map-reduce extraction, gap scoring (+momentum), briefs
  radar/research/          # brief-grounding helpers vendored from LearnX-Search (v7)
  learnx/                  # audio pipeline (from LearnX-CLI)
  dutch/                   # Dutch coach: curated wordlist + lesson + audio (v5)
  delivery/                # Telegram (DM + channel), email, PDF, waitlist, dev.to (v8)
  storage/                 # seen_skills.json, skill_memory.json, dutch_memory.json,
                           # trending_history.json (powers momentum), last_scored.json
  dashboard/               # static site (Radar/Dutch tabs) + podcast feed (v4/v8)
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
- v5: Alongside the dev lesson, a daily A2 Dutch lesson arrives — correct-by-design
  words (curated list), example sentences, a spoken Dutch MP3, spaced-repetition
  review, and a self-test — with a Dutch tab on the dashboard tracking your streak.
- v6: The Dutch track becomes a systematic path to **inburgering B1** — adaptive
  pacing, a growing B1 word bank, plus daily KNM (Dutch society), reading, and a
  weekly grammar focus. After 1–2 months the monthly mock + mastery % show real,
  measurable improvement across the exam skills.
- v7: The skill chosen each day is more often one genuinely rising across seven
  open-vocabulary sources (momentum-aware), and the brief teaching it is grounded in
  and cites real source text — not the model's priors.
- v8: The lesson reaches a real audience — a public Telegram channel (audio + PDF),
  a Spotify/Apple-listed podcast, and a weekly dev.to cross-post — while a waitlist
  captures demand for the personalized tier, all free-tier and storing no subscriber
  data.
- v9: The Dutch track adopts the **Delftse methode** (listen → imitate → produce):
  the daily MP3 leaves repeat-pauses after every sentence, the lesson ends with a
  fill-in-the-blanks production exercise, a static trainer page on Pages enforces
  the one-chance listening drill, and measured recall — not mere exposure — drives
  the spaced-repetition intervals. Every day's lesson is archived, so the trainer's
  lesson list can reopen any past day — a finished lesson stays visitable.