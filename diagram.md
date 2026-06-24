# LearnX-Radar — system diagrams

Mermaid diagrams of the whole system and each vertical. Grounded in `main.py`
(daily spine), `scripts/curate_aliases.py` + `.github/workflows/curate.yml` (weekly
curation), and the `dutch/` track. Render on GitHub, or in any Mermaid viewer.

Two scheduled entry points:

- **`radar.yml`** — daily 06:00 UTC, runs `python main.py` (the spine + both lesson tracks).
- **`curate.yml`** — Mondays 08:00 UTC, runs `python -m scripts.curate_aliases` (Loop C).

Three feedback loops: **A** lesson ratings, **B** Dutch recall, **C** alias curation.

---

## 1. Full system

```mermaid
flowchart TD
  %% ---------- Sources ----------
  subgraph SRC["Sources (scraped daily)"]
    direction LR
    GH["GitHub trending"]
    DEV["dev.to"]
    SO["Stack Overflow"]
    HN["Hacker News"]
    RD["Reddit"]
  end

  CRON["radar.yml - daily 06:00 UTC<br/>python main.py"]
  SRC --> CRON

  %% ---------- Daily spine ----------
  subgraph SPINE["Daily spine"]
    direction TB
    START["startup<br/>apply_learned_aliases() - canonicalize names<br/>ingest feedback: lesson ratings + Dutch recall"]
    SCRAPE["scrape -> filter_new<br/>(dedup vs seen_skills.json)"]
    EXTRACT["skill_extractor.extract<br/>(map-reduce LLM)"]
    SCORE["gap_scorer.score (+ momentum)<br/>-> pick today's top skill gap"]
    HIST[("DATA HISTORIAN<br/>trending_history.json")]
    START --> SCRAPE --> EXTRACT --> SCORE
    SCORE <--> HIST
  end
  CRON --> START

  %% ---------- Track A: dev ----------
  subgraph DEV_T["Track A - Dev lesson (discovers what to teach)"]
    direction TB
    BRIEF["brief_writer.write<br/>(grounded brief)"]
    CURR["curriculum.plan"]
    DIAL["dialogue.generate"]
    AUD["audio_builder.build (TTS mp3)"]
    BRIEF --> CURR --> DIAL --> AUD
  end
  SCORE --> BRIEF

  %% ---------- Track B: Dutch ----------
  subgraph NL_T["Track B - Dutch lesson (frozen bank + personalized)"]
    direction TB
    GATE{"backlog gate (day37)<br/>>= 5 lessons unsubmitted?"}
    NUDGE["pause + nudge<br/>(no new lesson, no SR advance)"]
    CEFR["advance_cefr (day41)<br/>recall-driven A2 -> A2+ -> B1"]
    COACH["coach (day36/41)<br/>missed words -> focus + directive (NIM)<br/>stuck words -> contrast drill (no LLM)"]
    SELECT["wordlist.select_for_today<br/>(frozen, human-reviewed bank)"]
    NLBUILD["lesson.build -> Delft audio (edge-tts)<br/>-> trainer JSON (dutch.html)"]
    GATE -- yes --> NUDGE
    GATE -- no --> CEFR --> COACH --> SELECT --> NLBUILD
  end
  SCORE --> GATE

  %% ---------- Deliver + persist ----------
  subgraph OUT["Deliver + Persist"]
    direction TB
    DELIVER["deliver: Telegram - email - dev.to draft<br/>Pages dashboard - podcast feed"]
    PERSIST["commit state to git"]
    DELIVER --> PERSIST
  end
  AUD --> DELIVER
  NLBUILD --> DELIVER
  NUDGE --> DELIVER

  STATE[("State (committed each run)<br/>seen_skills - skill_memory - last_scored<br/>trending_history - dutch_memory - dutch_lesson<br/>lessons/ - briefs/ - skill_aliases")]
  PERSIST --> STATE

  %% ---------- Loop C: weekly curation ----------
  subgraph CUR["Loop C - Weekly alias curation (curate.yml - Mon 08:00 UTC)"]
    direction TB
    SEM["semantic_match.py<br/>cosine shortlist (recall) ~23 pairs"]
    FILT{"Filter<br/>skip denylist.json pairs"}
    JUDGE["alias_curator.py - NIM LLM judge<br/>(precision): PostgreSQL != SQLite"]
    ALIAS[("skill_aliases.json")]
    LOG["skill_aliases_log.md - every verdict"]
    DMSG["Telegram DM"]
    DENY[("denylist.json")]
    HUMAN["HUMAN reviews log<br/>--reject a b (on the loop, not in it)"]
    SEM --> FILT --> JUDGE
    JUDGE --> ALIAS
    JUDGE --> LOG
    JUDGE --> DMSG
    HUMAN --> DENY --> FILT
  end
  HIST --> SEM

  %% ---------- Feedback arrows ----------
  ALIAS -. "Loop C: applied at next startup" .-> START
  DELIVER -. "Loop A: rating deep-link -> getUpdates" .-> START
  DELIVER -. "Loop B: Dutch recall -> getUpdates -> feeds coach" .-> COACH
```

---

## 2. Setup — one-time momentum-window tune (historical, not a feedback loop)

How `MOMENTUM_WINDOW_DAYS = 10` was chosen, once, in the cloud.

```mermaid
flowchart TD
  J5["Jun 5 - you sweep the degenerate window (6 days)"]
  ROUT["create a one-time cloud routine<br/>run_once_at = Jun 20 07:00"]
  SLEEP["PC sleeps 15 days (powered off)"]
  FIRE["Jun 20 07:00 - routine fires in the cloud<br/>sweep 18 days - pick the knee = 10d"]
  KNOB["MOMENTUM_WINDOW_DAYS = 10"]
  PR["shipped via PR #24"]
  J5 --> ROUT --> SLEEP --> FIRE --> KNOB --> PR
  KNOB -. "tunes the window knob" .-> SCORE["gap_scorer momentum (daily spine)"]
```

---

## 3. Daily spine (`main.py._run`)

The exact order the daily run executes.

```mermaid
flowchart TD
  CRON["radar.yml - 06:00 UTC - python main.py"]
  V["config.validate()"]
  AL["apply_learned_aliases()"]
  LM["load_memory()"]
  ING["_ingest_inbound - getUpdates<br/>lesson ratings -> skill_memory<br/>Dutch recall -> dutch_memory"]
  SCR["_scrape sources"]
  FN["filter_new (vs seen_skills.json)"]
  Q0{"anything new?"}
  EX["skill_extractor.extract (map-reduce LLM)"]
  SC["gap_scorer.score (+ momentum vs trending_history)"]
  TOP["gap_scorer.top -> today's skill gap"]
  SH["save_last_scored / save_trending_history"]
  DEVB["Track A: dev lesson build"]
  NLB["Track B: Dutch lesson build"]
  DEL["deliver (Telegram/email/dev.to)"]
  PR["persist state + commit"]
  DASH["refresh Pages dashboard"]
  CRON --> V --> AL --> LM --> ING --> SCR --> FN --> Q0
  Q0 -- no --> DASH
  Q0 -- yes --> EX --> SC --> TOP --> SH
  TOP --> DEVB
  TOP --> NLB
  DEVB --> DEL
  NLB --> DEL
  DEL --> PR --> DASH
```

---

## 4. Track A — Dev lesson (discovers what to teach)

```mermaid
flowchart TD
  SK["today's skill gap"]
  BW["brief_writer.write<br/>(grounded; uses scraped items)"]
  SB["save_brief -> briefs/ (Perplexity Q&A link)"]
  CP["curriculum.plan(difficulty)"]
  AC["brief_writer.action_step (outro CTA)"]
  DG["dialogue.generate(units, hook, action)"]
  AB["audio_builder.build<br/>-> lesson-YYYYMMDD-slug.mp3"]
  QZ["recall quiz targets the PREVIOUS lesson<br/>(real spaced retrieval)"]
  SK --> BW --> SB --> CP --> DG --> AB
  BW --> AC --> DG
  AB --> QZ
```

---

## 5. Track B — Dutch lesson (frozen bank + personalized)

Includes the day37 backlog gate, the day36 coach, and the day41 recall-driven
progression + contrast drill. Vocabulary is never invented — the LLM only
selects/emphasizes within the frozen `dutch/wordlist.json`.

```mermaid
flowchart TD
  DM[("dutch_memory.json")]
  GATE{"dutch_unsubmitted_streak >= DUTCH_BACKLOG_PAUSE_AFTER (5)?"}
  NUDGE["pause: nudge payload<br/>no new words, no SR advance"]
  CEFR["advance_cefr (day41, deterministic)<br/>recall at rung >= 0.85 over enough reports<br/>-> A2 -> A2+ -> B1 (raises prompt complexity)"]
  DS["detect_struggling (deterministic)<br/>recall_wrong > recall_right and >= MIN_MISSES"]
  Q{"any struggling words?"}
  PLAN["coach.plan - NIM (1 call)<br/>focus_ids (<= MAX_FOCUS) + directive"]
  CON["confusable_pairs (day41, no LLM)<br/>stuck word (wrong, never recalled)<br/>+ its top co-failed partner"]
  CL["append_log -> dutch_coach_log.md"]
  SEL["wordlist.select_for_today<br/>force_review_ids = focus + contrast ids"]
  BUILD["lesson.build(cefr, directive, contrast)<br/>-> Delft audio (edge-tts)"]
  TJ["trainer JSON -> dutch_lesson.json (dutch.html)"]
  DM --> GATE
  GATE -- yes --> NUDGE
  GATE -- no --> CEFR --> DS --> Q
  CEFR -- "level" --> BUILD
  Q -- no (cold start) --> SEL
  Q -- yes --> PLAN
  PLAN --> CL
  PLAN -- "focus_ids" --> SEL
  PLAN -- "directive" --> BUILD
  DS --> CON
  CON -- "force both ids" --> SEL
  CON -- "contrast section" --> BUILD
  SEL --> BUILD --> TJ
```

---

## 6. Loop C — Weekly alias curation (`curate.yml`)

Embeddings propose, the NIM LLM decides, accepted merges commit themselves back so
the next daily run collapses the variants. Human stays on the loop (audit + revert),
not in it (no approval blocks the daily lesson).

```mermaid
flowchart TD
  CR["curate.yml - Mon 08:00 UTC<br/>python -m scripts.curate_aliases"]
  TH[("trending_history.json")]
  SM["semantic_match - cosine shortlist<br/>(lexical embedder; NIM optional)"]
  FT{"drop denylist pairs"}
  JG["alias_curator.judge - NIM LLM (1 batched call)<br/>conservative: merge only true same-skill"]
  AF["aliases_from(accepted merges)"]
  SA[("skill_aliases.json")]
  LG["skill_aliases_log.md (every verdict)"]
  TG["Telegram DM (summary)"]
  CM["git commit + push [skip ci]"]
  DEN[("denylist.json")]
  HU["HUMAN: --reject a b"]
  ST["next daily run: apply_learned_aliases()"]
  CR --> TH --> SM --> FT --> JG --> AF --> SA --> CM
  JG --> LG
  AF --> TG
  HU --> DEN --> FT
  SA -. "applied at startup" .-> ST
```

---

## 7. Feedback loops A & B (deep-link, no server)

Both reuse the same trick: a delivered Telegram deep-link the learner taps; the next
morning's run reads it via `getUpdates` and folds it into state. Loop B's recall data
is exactly what the Dutch coach personalizes from.

```mermaid
sequenceDiagram
  participant L as Learner
  participant TG as Telegram / trainer (dutch.html)
  participant Bot as getUpdates (next run)
  participant ST as State

  Note over L,ST: Loop A - lesson rating
  TG-->>L: lesson + star deep-link buttons (start=lr_date_n)
  L->>TG: tap a star
  Bot->>ST: record_lesson_rating -> skill_memory.json

  Note over L,ST: Loop B - Dutch recall
  TG-->>L: Dutch lesson + trainer link
  L->>TG: practice, then Save results (start=dr_date_marks)
  Bot->>ST: record_dutch_recall -> dutch_memory.json
  ST->>ST: detect_struggling -> coach.plan personalizes next lesson
```