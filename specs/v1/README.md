# Specs — v1 (Daily Tech Lesson)

Spec-driven, same discipline as LearnX-CLI: every feature gets a written spec
before code. Each day's spec turns one stub from the skeleton into a working
component.

Suggested day breakdown (write one `dayN.md` per item before implementing):

1. `agents/` — implement all four `fetch()` collectors against live endpoints.
2. `radar/skill_extractor.py` — GLM-5.1 skill extraction prompt.
3. `radar/gap_scorer.py` + `radar/brief_writer.py` — score and author the brief.
4. `learnx/` — port curriculum + dialogue + audio_builder from LearnX-CLI.
5. `delivery/` — Telegram `sendAudio` + email MP3 attachment.
6. End-to-end run on the GitHub Actions free tier.
