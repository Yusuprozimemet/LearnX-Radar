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
Telegram deep links. Full detail in [Architecture](#architecture) below.

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

See the [Dutch coach](#dutch-coach) section below for the full design.

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
degrades gracefully — see [Configuration](#configuration).

---

# Architecture

The deep dive: how the daily run works, why the numbers are what they are,
every config flag, every state file.

## Pipeline (the daily run)

```
ingest feedback (lesson star ratings + Dutch recall reports, via getUpdates)
  -> scrape (7 sources) -> redact PII -> dedup
  -> extract skills (map-reduce + deterministic attribution)
  -> score gaps (demand x novelty x momentum) -> select today's topic
  -> write grounded brief (Jina + Exa, cited) -> plan curriculum
  -> generate dialogue -> build audio (edge-tts)
  -> build Dutch lesson (vocab + sentences + Delft audio + trainer JSON, archived)
  -> render PDFs -> deliver (Telegram DM + channel, email)
  -> persist state -> refresh dashboard + podcast feed
```

On its configured weekday the run also posts the personalization-waitlist CTA to
the channel and cross-posts the lesson to dev.to as a draft.

Each stage is wrapped so one failure produces a clear message instead of a silent
half-run; failures are collected and DM'd to the owner at the end
(`RUN_REPORT_ENABLED`). The Dutch branch is independent and fully guarded: any
failure there is logged and skipped so the developer lesson always ships.

## Accuracy & grounding

Each accuracy feature sits behind its own config flag for clean rollback:

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
- **Grounded briefs** (`GROUNDING_ENABLED`). Instead of writing from the skill
  name alone, the brief reads the actual sources that surfaced the skill
  (keyless Jina reader) plus fresh Exa web results, and cites a real
  `## Sources` list authored in code — the LLM never writes URLs. Read budget
  chosen by experiment ([scripts/exp_grounding.py](scripts/exp_grounding.py)).
  The grounding helpers in [radar/research/](radar/research/) are vendored from
  the sibling LearnX-Search.
- **Cross-day momentum** (`MOMENTUM_ENABLED`). Scoring looks back over
  `trending_history` (matched by canonical name) and boosts skills sustained and
  accelerating across days, while damping one-day spikes — orthogonal to the
  spaced-repetition novelty signal.

## Quality signals (closing the loop)

Both tracks measure whether the lessons *land*, not just that they shipped —
using the same zero-backend trick: a deep-link button opens
`https://t.me/<bot>?start=<payload>`, one tap sends that as a `/start` message
from the owner's own Telegram account, and the next morning's run reads it via
`getUpdates` and acknowledges the batch by advancing the offset server-side. No
webhook, no token in the browser, nothing persisted in transit.

- **Dev lessons — star ratings** (`LESSON_RATING_ENABLED`). The owner DM's
  lesson audio carries 1–5 star buttons (`lr_<YYMMDD>_<n>`); the rating is
  stamped on that day's lesson entry in `skill_memory.json`. The dashboard's
  lesson archive shows per-lesson stars and a rolling 30-day average. Buttons
  render on the owner DM only — ratings from other chats are ignored.
- **Dutch words — measured recall** (`DUTCH_RECALL_ENABLED`). The trainer
  page's "Save results" button reports per-word outcomes (`dr_<YYMMDD>_<marks>`,
  positional marks: `1` right / `0` wrong / `x` not trained); a failed word
  returns at the base interval, a recalled word spaces out further, an untrained
  word is untouched. The dashboard shows a rolling 30-day recall rate and the
  most-failed words. See [specs/v9](specs/v9).

Both payload kinds are parsed from the **same** getUpdates batch
([delivery/telegram_recall.py](delivery/telegram_recall.py)), because
acknowledging the batch drops every pending update.

## Dutch coach

A second daily track that teaches Dutch (A2, heading toward inburgering B1)
using the same engine and the **Delftse methode** (listen → imitate → produce).
Each run it:

- Selects a small themed word set — themes **alternate** day to day (everyday
  Dutch vs. tech-flavoured Dutch tied to the day's developer topic).
- Makes one LLM call to wrap those **exact** words in A2 example sentences and a
  short dialogue, then renders a Dutch-voice MP3 via edge-tts — in **Delft
  blocks**: vocabulary and dialogue sentence-by-sentence with a repeat pause
  sized to say each line back (then a self-check replay), and the dialogue
  straight through.
- Ends with a deterministic **fill-in-the-blanks** exercise (gatentekst) over
  today's new words — no LLM, so nothing can be wrong.
- Publishes the lesson as JSON for the **interactive trainer page**
  ([dutch.html](https://yusuprozimemet.github.io/LearnX-Radar/dutch.html)): the
  four Delft listening steps with a real player, checked cloze, and a
  one-listen-per-sentence luistertoets.
- **Archives every lesson** (a dated copy in `storage/lessons/` plus an
  `index.json` manifest) so the trainer's LESSEN tab lists past days next to
  their final scores — reopen any earlier lesson with audio streamed from the
  release CDN.
- Closes the loop with **measured recall** (see Quality signals above) and mixes
  in words due for spaced-repetition review, tracking a streak + CEFR level in
  [storage/dutch_memory.json](storage/dutch_memory.json).
- Appends a 🇳🇱 section to the email, sends a separate Dutch message/audio to
  Telegram (with a "Train this lesson" button), and adds a "Quiz me in Dutch"
  Perplexity link covering *yesterday's* words.

**Correct by design:** vocabulary is anchored to a frozen, human-reviewed word
bank ([dutch/wordlist.json](dutch/wordlist.json)). The LLM only writes sentences
around fixed words and never invents vocabulary — any generated word that isn't
in the bank is dropped, so a bad generation falls back to the verified gloss
rather than a wrong word. Grow the bank with the one-time generator (reviewed
before committing):

```
python -m dutch.build_wordlist --theme everyday --cefr A2 --count 40
```

The roadmap (KNM, reading, grammar, adaptive pacing toward B1) lives in
[specs/v5](specs/v5) and [specs/v6](specs/v6); the Delftse-methode slice
(paused audio, cloze, trainer, recall feedback, lesson archive) in
[specs/v9](specs/v9); see [plan/plan.md](plan/plan.md).

## Stack

- **LLM:** NVIDIA NIM (OpenAI-compatible) using `meta/llama-3.3-70b-instruct`,
  configured in [config.py](config.py).
- **Grounding:** keyless Jina Reader (`r.jina.ai`) for page reads + optional Exa
  neural web search (`EXA_API_KEY`) for fresh sources.
- **TTS:** edge-tts plus pydub (English co-host voices for dev lessons, `nl-NL`
  voices for Dutch); ffmpeg required for audio assembly.
- **PDF:** full-lesson PDFs via `xhtml2pdf` (pure-Python; the CI/cron runners
  install `libcairo2-dev` + `pkg-config` for its build).
- **Delivery:** Telegram Bot API (owner DM + a public broadcast channel) and
  Gmail SMTP.
- **Reach:** weekly dev.to cross-post via the Forem API (`DEVTO_API_KEY`, draft
  by default), and a Spotify-compliant podcast feed served from GitHub Pages.
- **Schedule:** the radar workflow runs at 06:00 UTC daily; dashboard + podcast
  feed deploy via GitHub Pages.

## Workflows

- **Radar run:** [.github/workflows/radar.yml](.github/workflows/radar.yml)
  runs `python main.py` and commits updated state files and briefs.
- **Pages:** [.github/workflows/pages.yml](.github/workflows/pages.yml) runs
  `python -m dashboard` and publishes the static HTML.
- **CI:** [.github/workflows/ci.yml](.github/workflows/ci.yml) runs
  `ruff check .` and `pytest` on every push and pull request.

## Podcast feed

The daily MP3s (developer + Dutch) are uploaded as assets on a single rolling
GitHub Release (tag `lessons`) by the radar workflow, and `podcast.xml` is
published alongside the dashboard on GitHub Pages — Dutch episodes interleave
with the dev lessons by date. The feed is **Spotify compliant**: it carries the
required iTunes directory tags, an owner email for ownership verification, and
square cover art (`cover.png`), and episodes are de-duplicated by audio GUID so
a re-run never doubles an episode.

Feed URL: `https://yusuprozimemet.github.io/LearnX-Radar/podcast.xml`

Audio is hosted on Releases (not committed to the repo and not on Pages) so it
never bloats git history or hits the Pages size cap — and it needs no credential
beyond the workflow's built-in `GITHUB_TOKEN`.

## Repository layout

<details>
<summary>Directory-by-directory guide</summary>

```
agents/     source collectors (GitHub, HN hiring + front page, Stack Overflow,
            dev.to, Reddit, Lobste.rs)
radar/      map-reduce skill extraction, gap scoring (+ momentum), grounded
            brief writing, PII scrubbing
radar/research/  brief-grounding helpers vendored from LearnX-Search: Jina
            reader (keyless), Exa search (key-gated), relevance filter
learnx/     curriculum, dialogue, audio_builder, LLM client
dutch/      Dutch coach: curated wordlist, lesson builder, Delft audio layout,
            cloze exercises (cloze.py), trainer lesson JSON (trainer.py)
delivery/   Telegram (DM + channel) & email delivery, full-lesson PDF (pdf.py),
            Perplexity follow-up links, deep-link feedback ingestion
            (telegram_recall.py: recall reports + lesson ratings), weekly
            waitlist CTA, weekly dev.to cross-post (devto_publisher.py)
dashboard/  static dashboard builder (Radar / Dutch tabs), the interactive
            Delft trainer page (dutch.html), podcast feed (feed.py),
            Open Graph preview + privacy.html
storage/    state files (seen_skills.json, skill_memory.json, last_scored.json,
            trending_history.json, dutch_memory.json, dutch_lesson.json,
            lessons/ — the per-day Dutch lesson archive + index.json)
briefs/     full lesson briefs (linked from lessons for Perplexity Q&A)
scripts/    one-off experiment harnesses (chunk size, grounding read budget,
            momentum window) — deletable, not part of the cron
specs/      per-day specs driving each slice (v1..v9)
output/     generated MP3 files and sample outputs
config.py   central configuration and model selection
main.py     daily pipeline entry point
```

</details>

## Configuration

Use [.env.example](.env.example) as the template. In CI the values come from
GitHub repo secrets (see [.github/workflows/radar.yml](.github/workflows/radar.yml)).

<details>
<summary>All env vars and flags</summary>

- **Required:** `NVIDIA_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
  `GMAIL_APP_PASSWORD`, `EMAIL_FROM`, `EMAIL_TO`.
- **Optional:** `GITHUB_TOKEN` (higher GitHub API rate limits); `EXA_API_KEY`
  (free at exa.ai — enables Exa web results in brief grounding; without it
  grounding falls back to reading the day's own source URLs via Jina).
- **Optional (public channel + waitlist):** `TELEGRAM_CHANNEL_ID` (e.g.
  `@learnradar`), `TELEGRAM_CHANNEL_BOT_TOKEN` (a separate public bot that
  admins the channel, so DMs/quiz stay on the personal bot), and `WAITLIST_URL`
  (hosted form link). All degrade gracefully — unset means delivery goes to the
  owner DM only and the CTA is skipped.
- **Optional (reach):** `DEVTO_API_KEY` (dev.to → Settings → Extensions → API
  Keys) enables the weekly dev.to cross-post; unset means it's skipped. It posts
  a draft by default (`DEVTO_PUBLISHED = False`) on `DEVTO_POST_WEEKDAY` (Mon).
- **Optional (feedback loops):** `TELEGRAM_BOT_USERNAME` — the main bot's public
  @username (without the @), used by the trainer page's "Save results" deep link
  and the lesson-rating star buttons. Unset means the buttons simply aren't
  rendered; payloads are accepted from `TELEGRAM_CHAT_ID` only
  (`DUTCH_RECALL_ENABLED`, `LESSON_RATING_ENABLED`).
- **Dutch coach:** needs **no new secrets** — it reuses the same LLM and
  edge-tts. Tune it via the `DUTCH_*` constants in [config.py](config.py)
  (enable/disable, words per day, review cap, voices, Delft pauses/cloze/trainer
  toggles); `DUTCH_ENABLED = True` by default.

Each accuracy feature sits behind its own flag for clean rollback:
`EXTRACTION_MAPREDUCE`, `GROUNDING_ENABLED`, `MOMENTUM_ENABLED`.

</details>

## State and outputs

<details>
<summary>Every state file and what it holds</summary>

- [storage/seen_skills.json](storage/seen_skills.json): dedup of source items
  already processed — a map of `id -> last-seen date`. A sighting expires after
  `SEEN_TTL_DAYS` (14) so trend sources (a repo still trending, a tag still hot)
  re-enter as fresh signal instead of being suppressed forever.
- [storage/skill_memory.json](storage/skill_memory.json): lesson history,
  spaced-repetition data, and per-lesson owner ratings.
- [storage/dutch_memory.json](storage/dutch_memory.json): Dutch vocab
  spaced-repetition state — per-word due dates, recall counters, streak, CEFR
  level, a Dutch lesson archive, and the trainer recall-report log. Created on
  the first Dutch run and committed by the workflow.
- `storage/dutch_lesson.json`: today's full Dutch lesson (text + translations +
  cloze + audio seek map + recall-report contract) for the trainer page —
  overwritten each run, copied to Pages by the deploy.
- `storage/lessons/`: the Dutch lesson archive — a dated JSON copy of every
  trainer lesson plus an `index.json` manifest, committed by the daily run and
  copied to Pages so the trainer can reopen any past day. Grows from the day the
  archive shipped; earlier lessons exist as audio only.
- [storage/last_scored.json](storage/last_scored.json): latest scoring for
  the dashboard. Scored from the full scrape each run (not just post-dedup
  items), so the board always shows the complete demand picture.
- [storage/trending_history.json](storage/trending_history.json): one ranking
  per day (kept ~60 days). Powers the dashboard's date replay **and** the
  cross-day momentum signal (prior days matched by canonical skill name).
- [briefs/](briefs): full lesson briefs, linked from each lesson for
  Perplexity Q&A.
- [output/](output): generated MP3 lessons — the developer lesson
  (`lesson-YYYYMMDD-<slug>.mp3`) and the Dutch lesson (`dutch-YYYYMMDD.mp3`).
- `dashboard/index.html`: generated static dashboard (not committed — rebuilt
  from state by the Pages deploy, and locally via `python -m dashboard`).
- [dashboard/dutch.html](dashboard/dutch.html): the static Delft trainer page
  (hand-written, not generated) — fetches `dutch_lesson.json` on Pages; progress
  lives in localStorage, results travel via the Telegram deep link (no backend).
- `dashboard/podcast.xml`: generated podcast feed (lesson MP3s hosted as assets
  on the `lessons` GitHub Release; built from committed state, published via
  Pages).

</details>

## Data and privacy

- All sources are public (GitHub Trending, HN "Who is Hiring?" + front page,
  Stack Overflow tag counts, dev.to RSS, Reddit `.rss`, Lobste.rs RSS). No
  accounts or private data are scraped.
- Brief grounding fetches public pages via Jina Reader and (optionally) Exa
  search; fetched page text is PII-scrubbed before it reaches the LLM,
  persistence, or delivery — treat Jina and Exa as third parties.
- PII (emails, phone numbers, @handles) is redacted from collected text at
  ingestion in [radar/privacy.py](radar/privacy.py) — before dedup, before
  the LLM, and before anything is persisted, delivered, or linked to Perplexity.
  Only `hn:<id>`-style keys (no source text) are persisted to
  [storage/seen_skills.json](storage/seen_skills.json).
- Text is processed by the NVIDIA NIM LLM, and each lesson links out to
  Perplexity — treat both as third parties.
- Dedup state expires after 14 days and is capped (5000 entries) so it does not
  grow without bound.
- **Dutch trainer:** progress stays in the browser's localStorage; recall
  reports (and lesson ratings) travel as a `/start` message **from the owner's
  own Telegram account to their own bot** (the page only builds a URL — no token
  in the browser, no backend). The pipeline accepts feedback from the owner chat
  only.
- **Subscribers & waitlist:** the Telegram channel stores **no** personal data
  on my side (Telegram manages membership). The early-access waitlist is a
  hosted form (Tally) that stores only the email you submit (+ optional
  segment/goals), under consent; see the
  [privacy policy](https://yusuprozimemet.github.io/LearnX-Radar/privacy.html).
  No subscriber list is ever committed to this repo.
