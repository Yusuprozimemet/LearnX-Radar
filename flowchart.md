# LearnX-Radar — Architecture & Data Flow

LearnX-Radar is a **cron-driven, stateless-server** pipeline: a single daily run
([main.py](main.py)) scrapes public developer signals, picks one skill gap, generates an
audio lesson (plus an independent Dutch lesson), delivers everything, and persists all
state as **committed JSON files** — no database, no backend. GitHub Actions is the
runtime; GitHub Pages is the frontend; Telegram `getUpdates` is the only inbound channel.

## 1. High-level architecture

```mermaid
flowchart TB
    subgraph Sources["Public sources (no auth)"]
        GH[GitHub Trending]
        HNH[HN Who-is-Hiring]
        HNF[HN Front Page]
        SO[Stack Overflow tag deltas]
        DEVTO[dev.to RSS]
        RED[Reddit RSS]
        LOB[Lobste.rs RSS]
    end

    subgraph Pipeline["Daily run — main.py (GitHub Actions, 06:00 UTC)"]
        AG[agents/ — fetch & normalize]
        RAD[radar/ — extract, score, write brief]
        LX[learnx/ — curriculum, dialogue, audio]
        NL[dutch/ — Dutch coach track]
        DEL[delivery/ — Telegram, email, dev.to, PDF]
        ST[storage/ — committed JSON state]
        DB[dashboard/ — static HTML + podcast feed]
    end

    subgraph External["External services"]
        LLM[NVIDIA NIM LLM<br/>OpenAI-compatible]
        TTS[edge-tts + pydub/ffmpeg]
        JINA[Jina Reader r.jina.ai]
        EXA[Exa search — optional]
    end

    subgraph Out["Outputs"]
        TG[Telegram DM + channel]
        EM[Gmail SMTP]
        DT[dev.to draft — weekly]
        PAGES[GitHub Pages<br/>dashboard, Dutch trainer, podcast.xml]
        REL[GitHub Release 'lessons'<br/>MP3 assets]
        PPLX[Perplexity deep links<br/>Q&A + recall quiz]
    end

    Sources --> AG --> RAD --> LX --> DEL
    RAD -. grounding .-> JINA & EXA
    RAD & LX & NL -. prompts .-> LLM
    LX & NL -. voices .-> TTS
    NL --> DEL
    DEL --> TG & EM & DT
    DEL -. links .-> PPLX
    Pipeline --> ST
    ST --> DB --> PAGES
    Pipeline -- MP3 upload --> REL
    REL -. enclosure URLs .-> PAGES
```

## 2. Daily pipeline data flow

The orchestration in [main.py](main.py) — every stage is guarded so one failure
degrades instead of killing the run; failures are collected and DM'd to the owner
at the end (`_report`).

```mermaid
flowchart TD
    START([cron 06:00 UTC]) --> VAL[config.validate + load_memory]
    VAL --> CTA[Weekly waitlist CTA to channel<br/><i>only on its weekday</i>]
    CTA --> SCRAPE

    subgraph Ingest["1 · Ingest"]
        SCRAPE["_scrape: 7 agents fetch()<br/>normalized items {id, source, title, url, text, meta}"]
        SCRUB[privacy.scrub — redact emails/phones/handles<br/><b>before</b> dedup, LLM, persistence, delivery]
        DEDUP["filter_new vs seen_skills.json<br/>(14-day TTL)"]
        SCRAPE --> SCRUB --> DEDUP
    end

    DEDUP -->|nothing new| QUIET[refresh dashboard, done]
    DEDUP --> EXTRACT

    subgraph Radar["2 · Radar (pick what to teach)"]
        EXTRACT["skill_extractor.extract — map-reduce LLM:<br/>chunk corpus → extract per chunk → merge aliases →<br/>deterministic per-source attribution (corpus scan)"]
        SCORE["gap_scorer.score — pure, no LLM:<br/>demand × novelty × table-stakes × known × goal × momentum"]
        TOP["top() → today's skill<br/>save_last_scored + save_trending_history"]
        EXTRACT --> SCORE --> TOP
    end

    TOP -->|no teachable gap| QUIET2[refresh dashboard, done]
    TOP --> BRIEF

    subgraph Learnx["3 · Lesson generation"]
        BRIEF["brief_writer.write — grounded brief:<br/>reads real source pages via Jina (+ Exa results),<br/>cited ## Sources authored in code, not by the LLM"]
        CUR["curriculum.plan — teaching units sized to duration"]
        DIA["dialogue.generate — ALEX/MAYA two-host script<br/>(concurrent per unit)"]
        AUD["audio_builder.build — edge-tts render →<br/>output/lesson-YYYYMMDD-slug.mp3"]
        BRIEF --> CUR --> DIA --> AUD
    end

    BRIEF -- save_brief --> BRIEFS[(briefs/*.md<br/>committed; seeds Perplexity Q&A)]
    AUD --> QUIZ["attach recall quiz: <i>previous</i> lesson's<br/>brief text → Perplexity deep link"]
    QUIZ --> DUTCH["3c · Dutch track (see §3)<br/>isolated — never blocks the dev lesson"]
    DUTCH --> SEND

    subgraph Deliver["4 · Deliver (channels independent)"]
        SEND["telegram_sender.send — MP3 + caption +<br/>full-lesson PDF (pdf.py) to DM + channel"]
        MAIL["email_sender.send — brief as HTML + MP3s"]
        DEVP["devto_publisher — weekly draft cross-post"]
        SEND --> MAIL --> DEVP
    end

    DEVP --> PERSIST

    subgraph Persist["5 · Persist (only after lesson produced)"]
        PERSIST["mark_seen → seen_skills.json<br/>record_lesson → skill_memory.json<br/>record_dutch_lesson → dutch_memory.json"]
    end

    PERSIST --> DASH["6 · dashboard.build — regenerate index.html<br/>from memory + today's ranking"]
    DASH --> REPORT["_report: DM collected stage failures to owner"]
    REPORT --> DONE([done])
```

### Scoring inputs (what feeds `gap_scorer`)

```mermaid
flowchart LR
    M[(skill_memory.json<br/>lesson history → novelty)] --> S
    H[(trending_history.json<br/>prior-day rankings → momentum)] --> S
    P[config.py<br/>KNOWN_SKILLS / LEARNING_GOALS / SOURCE_WEIGHTS] --> S
    X[skill mentions<br/>from extractor] --> S
    S{{gap_scorer.score}} --> R[ranked skills → top 1 taught,<br/>top N to dashboard]
```

## 3. Dutch coach track (Delftse methode)

An independent second track built in the same run (`_build_dutch` in
[main.py](main.py)) — any failure returns `(None, None)` so the developer lesson
always ships.

```mermaid
flowchart TD
    RECALL["telegram_recall.fetch_reports — read trainer<br/>'/start' recall reports via getUpdates (owner chat only)"]
    FOLD["record_dutch_recall — failed word due now,<br/>recalled word spaces out; saved immediately"]
    BANK[(dutch/wordlist.json<br/>frozen, human-reviewed word bank)]
    SEL["wordlist.select_for_today —<br/>new words + SR-due reviews, alternating theme<br/>(everyday ↔ tech, tied to today's dev skill)"]
    LES["lesson.build — ONE LLM call wraps the <b>exact</b> words<br/>in A2 sentences + dialogue; words never invented"]
    CLZ["cloze.py — deterministic fill-in-the-blanks (no LLM)"]
    DAUD["dutch/audio.build — nl-NL edge-tts in Delft blocks:<br/>sentence → repeat pause → self-check replay<br/>→ output/dutch-YYYYMMDD.mp3 + timings"]
    TRJ["trainer.build_payload → storage/dutch_lesson.json<br/>(text + translations + cloze + audio seek map)"]
    ATTACH["payload attached to lesson →<br/>Telegram message/audio + email 🇳🇱 section +<br/>'Quiz me in Dutch' Perplexity link (yesterday's words)"]
    DMEM[(storage/dutch_memory.json<br/>per-word due dates, streak, CEFR, recall log)]

    RECALL --> FOLD --> SEL
    DMEM --> FOLD
    BANK --> SEL --> LES --> CLZ --> DAUD --> TRJ
    DAUD --> ATTACH
    SEL -- record_dutch_lesson --> DMEM
```

### Recall feedback loop (no backend, no webhook)

```mermaid
sequenceDiagram
    participant Run as Daily run (Actions)
    participant Pages as GitHub Pages<br/>dutch.html trainer
    participant User as Learner's browser
    participant TG as Telegram Bot API

    Run->>Pages: commit dutch_lesson.json + deploy
    User->>Pages: open trainer, do listening/cloze/luistertoets
    Note over User: progress kept in localStorage
    User->>TG: tap "Save results" → /start deep link<br/>(own account → own bot, no token in browser)
    Note over TG: Telegram retains bot messages ~24h
    Run->>TG: next morning: getUpdates
    TG-->>Run: recall reports (owner chat only)
    Run->>Run: reschedule words in dutch_memory.json<br/>failed → due now · recalled → longer interval
```

## 4. State files (the "database")

All state lives in committed JSON — the Actions workflow commits it back after each
run, so state survives without external storage.

| File | Written by | Read by | Purpose |
|---|---|---|---|
| [storage/seen_skills.json](storage/seen_skills.json) | run (mark_seen) | run (filter_new) | dedup, 14-day TTL, capped 5000 |
| [storage/skill_memory.json](storage/skill_memory.json) | run (record_lesson) | scorer (novelty), quiz, dashboard | lesson history + SR data |
| [storage/last_scored.json](storage/last_scored.json) | run (save_last_scored) | dashboard | latest ranking (rebuildable without API keys) |
| [storage/trending_history.json](storage/trending_history.json) | run | scorer (momentum), dashboard date replay | one ranking per day, ~60 days |
| [storage/dutch_memory.json](storage/dutch_memory.json) | run (record_dutch_lesson / _recall) | Dutch selection, dashboard | per-word SR state, streak, CEFR, recall log |
| `storage/dutch_lesson.json` | run (trainer.build_payload) | dutch.html on Pages | today's trainer lesson, overwritten daily |
| [briefs/](briefs/) | run (save_brief) | Perplexity links, next-day quiz | full lesson briefs |
| [output/](output/) | audio builders | release upload | MP3s (hosted on the `lessons` Release, not Pages) |

## 5. Workflows & deployment

```mermaid
flowchart LR
    subgraph GHA["GitHub Actions"]
        RW["radar.yml — daily 06:00 UTC<br/>python main.py → commit state + briefs<br/>→ upload MP3s to 'lessons' Release"]
        PW["pages.yml — python -m dashboard<br/>(builder + feed; no API keys needed)"]
        CI["ci.yml — ruff check . + pytest<br/>on every push/PR"]
    end
    RW -- commit triggers --> PW
    PW --> PAGES["GitHub Pages:<br/>index.html · dutch.html ·<br/>podcast.xml · privacy.html"]
    PAGES --> SPOT[Spotify / podcast apps]
```

Key design point: the Pages workflow has **no secrets** — the dashboard and podcast
feed rebuild purely from committed state (`last_scored.json`, `skill_memory.json`,
`trending_history.json`, `dutch_memory.json`), which is why the run persists its
ranking instead of letting the dashboard re-run the radar.

## 6. Privacy edges

- PII (emails, phones, @handles) is scrubbed in [radar/privacy.py](radar/privacy.py)
  **at ingestion** — before dedup, the LLM, persistence, delivery, or Perplexity links.
- Committed state holds only skill/dedup keys (`hn:<id>`), never source text or subscribers.
- Third parties that see text: NVIDIA NIM (LLM), Jina/Exa (grounding), Perplexity (links).
- The Dutch trainer has no backend: progress is localStorage; recall reports travel as a
  Telegram deep link from the learner's own account; the pipeline accepts reports from
  the owner chat only.
