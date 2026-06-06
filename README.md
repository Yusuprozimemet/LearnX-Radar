# LearnX-Radar

LearnX-Radar is a self-updating curriculum engine that watches developer
signals for emerging skill gaps and auto-generates a personalized audio lesson.
Each lesson links to a Perplexity thread pre-loaded with the brief *text* for
follow-up Q&A (and a recall quiz), plus a static dashboard built from the
recorded state.

It also runs a second daily track — a **Dutch coach** (v5) — that rides the same
pipeline to teach Dutch (A2, heading toward inburgering B1): a small themed
vocabulary lesson with example sentences, a spoken Dutch MP3, spaced-repetition
review, and a recall quiz. See [Dutch coach](#dutch-coach-v5).

![LearnX-Radar overview](image.png)

## Subscribe (free)

- **Telegram channel — [t.me/learnradar](https://t.me/learnradar):** every daily
       lesson (developer + Dutch) as audio **plus the full lesson as a PDF**. Joining
       is the whole subscription — Telegram holds the member list, so **no personal
       data is stored** on our side.
- **Podcast:** add the [feed URL](#podcast-feed) to any podcast app.
- **Early access to *personalized* lessons:** a waitlist CTA is posted to the
       channel weekly; it links a hosted form (see [Privacy](#data-and-privacy)).

## What it does

- Collects signals from **seven** public sources: GitHub Trending, Hacker News
       (Who-is-Hiring + front page), Stack Overflow tag deltas, dev.to, Reddit, and
       Lobste.rs.
- Extracts skills via **map-reduce** over the corpus (chunked for recall, with
       **deterministic per-source attribution** — a corpus scan, not an LLM tally),
       scores gaps with spaced-repetition novelty **and a cross-day momentum signal**
       (rewards skills genuinely rising over time, damps one-day spikes), then selects
       a daily topic.
- Writes a teaching brief **grounded in the real source text** (read via Jina, plus
       fresh Exa web results when `EXA_API_KEY` is set) with cited `## Sources`; then
       plans a curriculum, generates dialogue, and builds one MP3 via edge-tts.
- Builds a second, independent **Dutch lesson** (vocab + sentences + dialogue +
       Dutch-voice MP3) from a curated word bank, with spaced-repetition review.
- Delivers both lessons to your Telegram DM **and an optional public broadcast
       channel** — audio + summary + the **full lesson as a PDF** (captions cap at
       1024 chars, so the PDF carries the complete, formatted lesson) — and to email
       (brief + MP3s).
- Posts a weekly **waitlist call-to-action** to the channel for upcoming
       personalized lessons (links a hosted form; no subscriber data stored here).
- Persists a knowledge memory and full briefs (whose text seeds each lesson's
       Perplexity follow-up Q&A and recall quiz).
- Redacts PII (emails, phone numbers, handles) from collected text at ingestion.
- Builds a static dashboard from committed state, with a Radar / Dutch tab toggle.
- Publishes a podcast RSS feed so the daily lessons land in your podcast app.

## Pipeline

```
scrape (7 sources) -> dedup -> extract skills (map-reduce + deterministic
                      attribution) -> score gaps (demand x novelty x momentum)
                      -> write grounded brief (Jina + Exa, cited)
                      -> plan curriculum -> generate dialogue -> build audio
                      -> build Dutch lesson (vocab + sentences + Dutch audio)
                      -> render PDFs -> deliver (Telegram DM + channel, email)
                      -> persist state -> refresh dashboard
```

(On its configured weekday the run also posts the personalization-waitlist CTA to
the channel.)

The Dutch branch is independent and fully guarded: any failure there is logged and
skipped so the developer lesson always ships. Set `DUTCH_ENABLED = False` in
[config.py](config.py) to turn the track off.

## Architecture & data flow

```mermaid
flowchart TB
  subgraph SRC["Input sources (public, 7)"]
    GH[GitHub Trending]
    HNH[HN Who-is-Hiring]
    HNF[HN Front Page]
    SO[Stack Overflow]
    DEV[dev.to]
    RED[Reddit]
    LOB[Lobste.rs]
  end

  PII["PII redaction (at ingestion)"]
  DEDUP["Dedup (vs seen_skills)"]

  subgraph ANALYZE["Analysis"]
    EXTRACT["Map-reduce extraction<br/>chunk -> LLM -> merge variants"]
    ATTR["Deterministic attribution<br/>corpus scan -> real source set"]
    SCORE["Gap scoring<br/>demand x novelty x momentum"]
    TOP{Top skill of the day}
    EXTRACT --> ATTR --> SCORE --> TOP
  end

  subgraph DEV_PIPE["Developer lesson"]
    BRIEF["Grounded brief<br/>Jina read + Exa, cited Sources"]
    CURR[Curriculum] --> DIAL[Dialogue] --> AUD[Audio MP3 - edge-tts]
    BRIEF --> CURR
  end

  subgraph DUTCH["Dutch coach (independent track)"]
    DW[Select words + SRS] --> DL[Lesson LLM] --> DA[Dutch MP3]
  end

  PDF[Render full-lesson PDFs]

  subgraph DELIVER["Delivery & outputs"]
    TG["Telegram<br/>your DM + public channel<br/>audio + full-lesson PDF"]
    EMAIL[Email: brief + MP3s]
    QUIZ[Quiz polls + Perplexity links]
    WAIT[Weekly waitlist CTA]
    DASH[Static dashboard]
    FEED[Podcast RSS]
  end

  subgraph STATE["State / memory (committed JSON)"]
    SEEN[(seen_skills)]
    SM[(skill_memory)]
    LS[(last_scored)]
    HIST[(trending_history)]
    DM[(dutch_memory)]
  end

  NIM[[NVIDIA NIM LLM]]

  %% main data flow
  SRC --> PII --> DEDUP --> EXTRACT
  TOP --> BRIEF
  AUD --> PDF
  DA --> PDF
  PDF --> TG
  PDF --> EMAIL
  TOP --> QUIZ
  WAIT --> TG

  %% state reads/writes
  DEDUP --> SEEN
  AUD --> SM
  SCORE --> LS
  SCORE --> HIST
  DA --> DM
  HIST -. momentum .-> SCORE
  LS --> DASH
  AUD --> FEED
  DA --> FEED

  %% shared LLM provider
  NIM -. powers .-> EXTRACT
  NIM -.-> BRIEF
  NIM -.-> DIAL
  NIM -.-> DL
```

Privacy-relevant edges: the public channel and the waitlist store **no** personal
data on our side (see [Data and privacy](#data-and-privacy)); committed state JSON
holds only skill/dedup data, never source PII or subscribers.

## Accuracy & grounding (v7)

Three pieces sharpen *what* gets taught and *how grounded* the lesson is — each
behind a config flag for clean rollback:

- **Open-vocabulary discovery (7 sources).** Reddit, the HN front page, and
       Lobste.rs are open-vocabulary feeds, so the radar can surface skills it was
       never pre-configured to watch — not just a fixed tag/language list. Per-source
       weights (`SOURCE_WEIGHTS`) keep real demand (HN Hiring, Stack Overflow) above
       community buzz.
- **Map-reduce extraction + deterministic attribution** (`EXTRACTION_MAPREDUCE`).
       The corpus is chunked and skills extracted per chunk (recall), variants merged
       (`SKILL_ALIASES`), then each skill's source set is computed by **scanning the
       corpus** rather than trusting the LLM to tally — so the demand weight is exact.
       Chunk size was chosen by experiment ([scripts/exp_extraction.py](scripts/exp_extraction.py)).
- **Grounded briefs** (`GROUNDING_ENABLED`). Instead of writing from the skill name
       alone, the brief reads the actual sources that surfaced the skill (keyless Jina
       reader) plus fresh Exa web results, and cites a real `## Sources` list authored
       in code (the LLM never writes URLs). Read budget chosen by experiment
       ([scripts/exp_grounding.py](scripts/exp_grounding.py)). The grounding helpers in
       [radar/research/](radar/research/) are vendored from the sibling LearnX-Search.
- **Cross-day momentum** (`MOMENTUM_ENABLED`). Scoring looks back over
       `trending_history` (matched by canonical name) and boosts skills sustained and
       accelerating across days, while damping one-day spikes — orthogonal to the
       spaced-repetition novelty signal.

## Repository layout

```
agents/     source collectors (GitHub, HN hiring + front page, Stack Overflow,
            dev.to, Reddit, Lobste.rs)
radar/      map-reduce skill extraction, gap scoring (+ momentum), grounded
            brief writing, PII scrubbing
radar/research/  brief-grounding helpers vendored from LearnX-Search: Jina
            reader (keyless), Exa search (key-gated), relevance filter
learnx/     curriculum, dialogue, audio_builder, LLM client
dutch/      Dutch coach: curated wordlist, lesson builder, Dutch audio (v5)
delivery/   Telegram (DM + channel) & email delivery, full-lesson PDF (pdf.py),
            Perplexity follow-up links, weekly waitlist CTA
dashboard/  static dashboard builder (Radar / Dutch tabs) + privacy.html
storage/    state files (seen_skills.json, skill_memory.json, last_scored.json,
            trending_history.json, dutch_memory.json)
briefs/     full lesson briefs (linked from lessons for Perplexity Q&A)
scripts/    one-off experiment harnesses (chunk size, grounding read budget,
            momentum window) — deletable, not part of the cron
specs/      per-day specs driving each slice (v1..v7)
output/     generated MP3 files and sample outputs
config.py   central configuration and model selection
main.py     daily pipeline entry point
```

## Stack

- LLM: NVIDIA NIM (OpenAI-compatible) using `meta/llama-3.3-70b-instruct`
       configured in [config.py](config.py).
- Grounding: keyless Jina Reader (`r.jina.ai`) for page reads + optional Exa
       neural web search (`EXA_API_KEY`) for fresh sources.
- TTS: edge-tts plus pydub (English co-host voices for dev lessons, `nl-NL` voices
       for Dutch lessons); ffmpeg required for audio assembly.
- PDF: full-lesson PDFs via `xhtml2pdf` (pure-Python; the CI/cron runners install
       `libcairo2-dev` + `pkg-config` for its build).
- Delivery: Telegram Bot API (your DM **+ a public broadcast channel**) and Gmail SMTP.
- Schedule: radar workflow runs at 06:00 UTC every day; dashboard deploys via
       GitHub Pages.

## Configuration

- Required env vars: `NVIDIA_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
       `GMAIL_APP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`.
- Optional: `GITHUB_TOKEN` (higher GitHub API rate limits); `EXA_API_KEY` (free at
       exa.ai — enables Exa web results in brief grounding; without it grounding falls
       back to reading the day's own source URLs via Jina).
- Optional (public channel + waitlist): `TELEGRAM_CHANNEL_ID` (e.g. `@learnradar`),
       `TELEGRAM_CHANNEL_BOT_TOKEN` (a separate public bot that admins the channel, so
       DMs/quiz stay on the personal bot), and `WAITLIST_URL` (hosted form link). All
       degrade gracefully — unset means delivery goes to your DM only and the CTA is
       skipped.
- The Dutch coach needs **no new secrets** — it reuses the same LLM and edge-tts.
       Tune it via the `DUTCH_*` constants in [config.py](config.py) (enable/disable,
       words per day, review cap, voices); `DUTCH_ENABLED = True` by default.
- Use [.env.example](.env.example) as the template.

## Dutch coach (v5)

A second daily track that teaches Dutch (A2, heading toward inburgering B1) using the
same engine. Each run it:

- Selects a small themed word set — themes **alternate** day to day (everyday Dutch
       vs. tech-flavoured Dutch tied to the day's developer topic).
- Makes one LLM call to wrap those **exact** words in A2 example sentences and a short
       dialogue, then renders a Dutch-voice MP3 via edge-tts.
- Mixes in words **due for spaced-repetition review** and tracks a streak + CEFR level
       in [storage/dutch_memory.json](storage/dutch_memory.json).
- Appends a 🇳🇱 section to the email, sends a separate Dutch message/audio to Telegram,
       and adds a "Quiz me in Dutch" Perplexity link covering *yesterday's* words.

**Correct by design:** vocabulary is anchored to a frozen, human-reviewed word bank
([dutch/wordlist.json](dutch/wordlist.json)). The LLM only writes sentences around fixed
words and never invents vocabulary — any generated word that isn't in the bank is
dropped, so a bad generation falls back to the verified gloss rather than a wrong word.
Grow the bank with the one-time generator (reviewed before committing):

```
python -m dutch.build_wordlist --theme everyday --cefr A2 --count 40
```

The roadmap (KNM, reading, grammar, adaptive pacing toward B1) lives in
[specs/v5](specs/v5) and [specs/v6](specs/v6); see [plan/plan.md](plan/plan.md).

## Local usage

```
pip install -r requirements.txt
# copy the example env file to .env and fill in values
python main.py
```

Other entry points:

```
python -m dashboard
```

In CI, the env values come from GitHub repo secrets (see
[.github/workflows/radar.yml](.github/workflows/radar.yml)).

## Workflows

- Radar run: [.github/workflows/radar.yml](.github/workflows/radar.yml) runs
       `python main.py` and commits updated state files and briefs.
- Pages: [.github/workflows/pages.yml](.github/workflows/pages.yml) runs
       `python -m dashboard` and publishes the static HTML.

## State and outputs

- [storage/seen_skills.json](storage/seen_skills.json): dedup of source items
       already processed — a map of `id -> last-seen date`. A sighting expires
       after `SEEN_TTL_DAYS` (14) so trend sources (a repo still trending, a tag
       still hot) re-enter as fresh signal instead of being suppressed forever.
- [storage/skill_memory.json](storage/skill_memory.json): lesson history and
       spaced repetition data.
- [storage/dutch_memory.json](storage/dutch_memory.json): Dutch vocab
       spaced-repetition state — per-word due dates, streak, CEFR level, and a Dutch
       lesson archive. Created on the first Dutch run and committed by the workflow.
- [storage/last_scored.json](storage/last_scored.json): latest scoring for the
       dashboard. Scored from the full scrape each run (not just post-dedup
       items), so the board always shows the complete demand picture and updates
       on every run.
- [storage/trending_history.json](storage/trending_history.json): one ranking per
       day (kept ~60 days). Powers the dashboard's date replay **and** the cross-day
       momentum signal (prior days are matched by canonical skill name).
- [briefs](briefs): full lesson briefs, linked from each lesson for Perplexity Q&A.
- [output](output): generated MP3 lessons — the developer lesson
       (`lesson-YYYYMMDD-<slug>.mp3`) and the Dutch lesson (`dutch-YYYYMMDD.mp3`).
- [dashboard/index.html](dashboard/index.html): generated static dashboard.
- `dashboard/podcast.xml`: generated podcast feed (lesson MP3s hosted as assets on
       the `lessons` GitHub Release; built from committed state, published via Pages).

## Podcast feed

The daily MP3s (developer lesson + Dutch lesson) are uploaded as assets on a single
rolling GitHub Release (tag `lessons`) by the radar workflow, and `podcast.xml` is
published alongside the dashboard on GitHub Pages — Dutch episodes interleave with
the dev lessons by date. Subscribe in any podcast app (Pocket Casts, Apple Podcasts,
AntennaPod) by adding the feed URL:

```
https://yusuprozimemet.github.io/LearnX-Radar/podcast.xml
```

Audio is hosted on Releases (not committed to the repo and not on Pages) so it
never bloats git history or hits the Pages size cap — and it needs no credential
beyond the workflow's built-in `GITHUB_TOKEN`.

## Data and privacy

- All sources are public (GitHub Trending, HN "Who is Hiring?" + front page,
       Stack Overflow tag counts, dev.to RSS, Reddit `.rss`, Lobste.rs RSS). No
       accounts or private data are scraped.
- Brief grounding fetches public pages via Jina Reader and (optionally) Exa
       search; fetched page text is PII-scrubbed before it reaches the LLM,
       persistence, or delivery — treat Jina and Exa as third parties.
- PII (emails, phone numbers, @handles) is redacted from collected text at
       ingestion in [radar/privacy.py](radar/privacy.py) — before dedup, before
       the LLM, and before anything is persisted, delivered, or linked to
       Perplexity. Only `hn:<id>`-style keys (no source text) are persisted to
       [storage/seen_skills.json](storage/seen_skills.json).
- Text is processed by the NVIDIA NIM LLM, and each lesson links out to
       Perplexity — treat both as third parties.
- Dedup state expires after 14 days and is capped (5000 entries) so it does not
       grow without bound.
- **Subscribers & waitlist:** the Telegram channel stores **no** personal data on
       our side (Telegram manages membership). The early-access waitlist is a hosted
       form (Tally) that stores only the email you submit (+ optional segment/goals),
       under consent; see the [privacy policy](https://yusuprozimemet.github.io/LearnX-Radar/privacy.html).
       No subscriber list is ever committed to this repo.

## Tests

```
pytest
ruff check .
```
