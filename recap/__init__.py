"""The /recap Telegram Q&A bot.

A scheduled GitHub Actions workflow runs one poll cycle every ~15 min: read
pending Telegram updates, answer any `/recap <question>` from the configured
chat (grounded in lesson history + full briefs), reply, and confirm the offset
so they aren't re-processed. No server, no local offset state — Telegram tracks
the confirmed offset. See .github/workflows/recap.yml.
"""
