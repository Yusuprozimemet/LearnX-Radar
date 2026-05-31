# LearnX-Radar

LearnX-Radar is a self-updating curriculum engine that watches developer
signals for emerging skill gaps and auto-generates a personalized audio lesson.
Each lesson links to a Perplexity thread pre-loaded with the brief for follow-up
Q&A, plus a static dashboard built from the recorded state.

![LearnX-Radar overview](image.png)

## What it does

- Collects signals from GitHub Trending, Hacker News Who is Hiring, dev.to RSS,
       and Stack Overflow tag deltas.
- Extracts skills, scores gaps, and selects a daily topic.
- Writes a teaching brief, plans a curriculum, generates dialogue, and builds
       one MP3 via edge-tts.
- Delivers the lesson to Telegram (audio + summary) and email (brief + MP3).
- Persists a knowledge memory and full briefs (linked from each lesson for
       Perplexity follow-up Q&A).
- Redacts PII (emails, phone numbers, handles) from collected text at ingestion.
- Builds a static dashboard from committed state.
- Publishes a podcast RSS feed so the daily lesson lands in your podcast app.

## Pipeline

```
scrape -> dedup -> extract skills -> score gaps -> write brief
                      -> plan curriculum -> generate dialogue -> build audio
                      -> deliver (Telegram + email) -> persist state -> refresh dashboard
```

## Repository layout

```
agents/     source collectors (GitHub, HN, dev.to, Stack Overflow)
radar/      skill extraction, gap scoring, brief writing
learnx/     curriculum, dialogue, audio_builder, LLM client
delivery/   Telegram and email delivery (+ Perplexity follow-up link)
dashboard/  static dashboard builder
storage/    state files (seen_skills.json, skill_memory.json, last_scored.json)
briefs/     full lesson briefs (linked from lessons for Perplexity Q&A)
output/     generated MP3 files and sample outputs
config.py   central configuration and model selection
main.py     daily pipeline entry point
```

## Stack

- LLM: NVIDIA NIM (OpenAI-compatible) using `meta/llama-3.3-70b-instruct`
       configured in [config.py](config.py).
- TTS: edge-tts plus pydub; ffmpeg required for audio assembly.
- Delivery: Telegram Bot API and Gmail SMTP.
- Schedule: radar workflow runs at 06:00 UTC every day; dashboard deploys via
       GitHub Pages.

## Configuration

- Required env vars: `NVIDIA_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
       `GMAIL_APP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`.
- Optional: `GITHUB_TOKEN` (higher GitHub API rate limits).
- Use [.env.example](.env.example) as the template.

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
- [storage/last_scored.json](storage/last_scored.json): latest scoring for the
       dashboard.
- [briefs](briefs): full lesson briefs, linked from each lesson for Perplexity Q&A.
- [output](output): generated MP3 lessons (for example, lesson-YYYYMMDD.mp3).
- [dashboard/index.html](dashboard/index.html): generated static dashboard.
- `dashboard/podcast.xml`: generated podcast feed (lesson MP3s hosted as assets on
       the `lessons` GitHub Release; built from committed state, published via Pages).

## Podcast feed

The daily MP3 is uploaded as an asset on a single rolling GitHub Release (tag
`lessons`) by the radar workflow, and `podcast.xml` is published alongside the
dashboard on GitHub Pages. Subscribe in any podcast app (Pocket Casts, Apple
Podcasts, AntennaPod) by adding the feed URL:

```
https://yusuprozimemet.github.io/LearnX-Radar/podcast.xml
```

Audio is hosted on Releases (not committed to the repo and not on Pages) so it
never bloats git history or hits the Pages size cap — and it needs no credential
beyond the workflow's built-in `GITHUB_TOKEN`.

## Data and privacy

- All sources are public (GitHub Trending, HN "Who is Hiring?", dev.to RSS,
       Stack Overflow tag counts). No accounts or private data are scraped.
- PII (emails, phone numbers, @handles) is redacted from collected text at
       ingestion in [radar/privacy.py](radar/privacy.py) — before dedup, before
       the LLM, and before anything is persisted, delivered, or linked to
       Perplexity. Only `hn:<id>`-style keys (no source text) are persisted to
       [storage/seen_skills.json](storage/seen_skills.json).
- Text is processed by the NVIDIA NIM LLM, and each lesson links out to
       Perplexity — treat both as third parties.
- Dedup state expires after 14 days and is capped (5000 entries) so it does not
       grow without bound.

## Tests

```
pytest
ruff check .
```
