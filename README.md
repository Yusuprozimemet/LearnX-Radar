# LearnX-Radar

> **A self-updating curriculum engine: it watches real developer signals for emerging skill gaps and ships you a grounded audio lesson every day — on zero backend.**

[![Live dashboard](https://img.shields.io/badge/dashboard-live-brightgreen)](https://yusuprozimemet.github.io/LearnX-Radar/)
[![Listen on Spotify](https://img.shields.io/badge/Spotify-listen-1DB954?logo=spotify&logoColor=white)](https://open.spotify.com/show/033tPjkKDj5xF09FQC0Di7)
[![Join on Telegram](https://img.shields.io/badge/Telegram-join-26A5E4?logo=telegram&logoColor=white)](https://t.me/learnradar)


Every morning a GitHub Actions cron scrapes **seven public sources** (GitHub
Trending, HN hiring + front page, Stack Overflow, dev.to, Reddit, Lobste.rs),
scores skill gaps by **demand × novelty × momentum**, writes a teaching brief
**grounded in the actual source text** with real citations, and delivers it as a
podcast-style MP3 — to Telegram, email, Spotify, and a live dashboard.

```
scrape (7 sources) -> extract skills -> score gaps -> grounded brief
   -> curriculum -> dialogue -> audio -> deliver -> dashboard + podcast feed
```

There is no server anywhere: committed JSON is the database, GitHub Releases is
the audio CDN, GitHub Pages is the frontend, and feedback comes back through
Telegram deep links. Full detail in **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

<table align="center">
  <tr>
    <td align="center"><a href="https://yusuprozimemet.github.io/LearnX-Radar/"><b>Live skill radar</b></a></td>
    <td align="center"><a href="https://yusuprozimemet.github.io/LearnX-Radar/dutch.html"><b>Dutch trainer</b></a></td>
  </tr>
  <tr>
    <td><img src="image2.png" alt="LearnX-Radar dashboard — daily trending-skills radar with the Dutch tab and Telegram/Spotify links" width="380" /></td>
    <td><img src="image3.png" alt="Dutch trainer — Delft listening step with audio player, tap-to-play dialogue lines and translations" width="380" /></td>
  </tr>
</table>

## Subscribe (free)

- **Telegram — [t.me/learnradar](https://t.me/learnradar):** every daily lesson
  as audio plus the full lesson as a PDF. Joining is the whole subscription —
  Telegram holds the member list, so no personal data is stored on my side.
- **Spotify — [listen here](https://open.spotify.com/show/033tPjkKDj5xF09FQC0Di7):**
  the lessons as a daily podcast, or add the
  [feed URL](https://yusuprozimemet.github.io/LearnX-Radar/podcast.xml) to any
  podcast app.
- **Waitlist for *personalized* lessons — [tally.so/r/WOqPdP](https://tally.so/r/WOqPdP):**
  early access to lessons matched to your stack & goals (individuals & teams).

## Why it's built this way

The interesting part isn't that an LLM writes lessons — it's where the LLM is
**not** trusted:

- **Deterministic where it must be exact.** Per-source skill attribution is a
  corpus scan, not an LLM tally; the brief's `## Sources` list is authored in
  code (the LLM never writes URLs); the Dutch cloze exercise is generated
  without any LLM, so nothing can be wrong.
- **Numbers chosen by experiment.** Extraction chunk size and the grounding
  read budget were swept against the real corpus with committed harnesses in
  [scripts/](scripts/) — none of the constants are guesses.
- **Feedback measured, both tracks.** The dashboard tracks a measured 30-day
  recall rate for Dutch words and a 1–5 owner rating per developer lesson —
  both reported through one-tap Telegram deep links (`/start` messages from
  your own account: no webhook, no token in the browser).
- **Privacy as architecture.** PII is redacted at ingestion — before dedup,
  before the LLM, before anything is persisted or delivered. The channel and
  waitlist store no subscriber data in this repo.
- **Graceful degradation.** Every optional secret degrades cleanly, the Dutch
  branch is guarded so the dev lesson always ships, and stage failures are
  DM'd to the owner instead of hiding in Actions logs.

## The Dutch track

The same engine runs a second daily lesson: a **Dutch coach** (A2 → inburgering
B1) built on the **Delftse methode** (listen → imitate → produce) — audio with
repeat pauses, an [interactive trainer page](https://yusuprozimemet.github.io/LearnX-Radar/dutch.html)
with checked exercises, and spaced repetition driven by **measured recall**:
what you can produce, not just what you were sent. Vocabulary is anchored to a
frozen, human-reviewed word bank — the LLM writes sentences *around* fixed
words and can never invent vocabulary.

See [the Dutch coach section of ARCHITECTURE.md](docs/ARCHITECTURE.md#dutch-coach)
for the full design.

## Quick start

```
pip install -r requirements.txt
# copy .env.example to .env and fill in values
python main.py            # one full daily run
python -m dashboard       # rebuild the static dashboard from committed state
pytest && ruff check .    # tests + lint (same as CI)
```

Required env vars: `NVIDIA_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
`GMAIL_APP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`. Everything else is optional and
degrades gracefully — see
[Configuration](docs/ARCHITECTURE.md#configuration).

## Data and privacy

All scraped sources are public; PII is redacted at ingestion; the Dutch
trainer's progress stays in your browser and its reports travel from your own
Telegram account to your own bot. Details in
[ARCHITECTURE.md](docs/ARCHITECTURE.md#data-and-privacy) and the
[privacy policy](https://yusuprozimemet.github.io/LearnX-Radar/privacy.html).

## More

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — pipeline, config flags, state
  files, workflows, podcast feed, Dutch coach internals
- [flowchart.md](flowchart.md) — visual pipeline walkthrough
- [specs/](specs/) — the per-day specs that drove each slice (v1..v9)
