# LearnX-Radar

A self-updating curriculum engine that watches the developer world for emerging
skill gaps and auto-generates a personalized audio lesson, delivered every
morning — without a human author.

It combines two systems: **Daily-CronJob** (scheduled scrape → summarize →
deliver) and **LearnX-CLI** (markdown → audio lesson via LLM + TTS). A cron run
detects rising skills, writes a teaching brief, turns it into an MP3 lesson, and
sends it to Telegram and email. See [plan/plan.md](plan/plan.md) for the full design.

## Pipeline

```
scrape → dedup → extract skills → score gaps → write brief
       → plan curriculum → generate dialogue → build audio
       → deliver (Telegram + email) → persist state
```

## Layout

```
agents/     data collection — github_trending, hn_hiring, devto, stackoverflow
radar/      skill_extractor, gap_scorer, brief_writer
learnx/     audio pipeline — llm, curriculum, dialogue, audio_builder
delivery/   telegram_sender, email_sender
storage/    state I/O + seen_skills.json, skill_memory.json
dashboard/  static skill-radar site (v3)
specs/      day-by-day specs (written before code)
plan/       design docs
config.py   sources, limits, model
main.py     orchestrator / entry point
```

## Stack

- **LLM:** NVIDIA NIM (`z-ai/glm-5.1`), OpenAI-compatible, free tier — every LLM call.
- **TTS:** edge-tts (no API key). Requires `ffmpeg` on PATH for assembly.
- **Delivery:** Telegram bot + Gmail SMTP.
- **Schedule:** GitHub Actions cron, 06:00 UTC weekdays.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in NVIDIA_API_KEY, Telegram, Gmail
python main.py
```

In CI, the `.env` values come from GitHub repo secrets (see
[.github/workflows/radar.yml](.github/workflows/radar.yml)).

## Status

Scaffold in place. Module bodies that talk to live endpoints or the LLM raise
`NotImplementedError` and are filled in spec-by-spec — see
[specs/v1/README.md](specs/v1/README.md). The orchestration in `main.py` is the
contract those stubs implement.
