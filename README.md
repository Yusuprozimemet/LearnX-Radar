# LearnX-Radar

LearnX-Radar is a self-updating curriculum engine that watches developer
signals for emerging skill gaps and auto-generates a personalized audio lesson.
It also provides a /recap Telegram Q&A bot and a static dashboard built from
the recorded state.

![LearnX-Radar overview](image.png)

## What it does

- Collects signals from GitHub Trending, Hacker News Who is Hiring, dev.to RSS,
       and Stack Overflow tag deltas.
- Extracts skills, scores gaps, and selects a daily topic.
- Writes a teaching brief, plans a curriculum, generates dialogue, and builds
       one MP3 via edge-tts.
- Delivers the lesson to Telegram (audio + summary) and email (brief + MP3).
- Persists a knowledge memory and full briefs for recap Q&A.
- Builds a static dashboard from committed state.

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
delivery/   Telegram and email delivery
recap/      /recap Telegram Q&A bot (polling)
dashboard/  static dashboard builder
storage/    state files (seen_skills.json, skill_memory.json, last_scored.json)
briefs/     full lesson briefs (used by recap)
output/     generated MP3 files and sample outputs
config.py   central configuration and model selection
main.py     daily pipeline entry point
```

## Stack

- LLM: NVIDIA NIM (OpenAI-compatible) using `meta/llama-3.3-70b-instruct`
       configured in [config.py](config.py).
- TTS: edge-tts plus pydub; ffmpeg required for audio assembly.
- Delivery: Telegram Bot API and Gmail SMTP.
- Schedule: radar workflow runs at 06:00 UTC on weekdays; recap workflow is
       manual by default; dashboard deploys via GitHub Pages.

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
python -m recap
python -m dashboard
```

In CI, the env values come from GitHub repo secrets (see
[.github/workflows/radar.yml](.github/workflows/radar.yml)).

## Workflows

- Radar run: [.github/workflows/radar.yml](.github/workflows/radar.yml) runs
       `python main.py` and commits updated state files and briefs.
- Recap bot: [.github/workflows/recap.yml](.github/workflows/recap.yml) runs
       `python -m recap` on manual dispatch. Add a cron schedule if you want
       automatic polling.
- Pages: [.github/workflows/pages.yml](.github/workflows/pages.yml) runs
       `python -m dashboard` and publishes the static HTML.

## State and outputs

- [storage/seen_skills.json](storage/seen_skills.json): dedup of source items
       already taught.
- [storage/skill_memory.json](storage/skill_memory.json): lesson history and
       spaced repetition data.
- [storage/last_scored.json](storage/last_scored.json): latest scoring for the
       dashboard.
- [briefs](briefs): full lesson briefs used by recap Q&A.
- [output](output): generated MP3 lessons (for example, lesson-YYYYMMDD.mp3).
- [dashboard/index.html](dashboard/index.html): generated static dashboard.

## Tests

```
pytest
ruff check .
```
