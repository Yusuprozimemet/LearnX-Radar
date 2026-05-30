# v3 / Day 8 — Skill-radar dashboard (static HTML → GitHub Pages)

**Goal:** make the radar visible. One static HTML page, regenerated each run,
showing what the developer world is demanding, what you've learned, and the
gaps between — plus a lesson archive. No backend; pure render from state.

## Data sources

- `skill_memory.json` — `skills` (coverage: `times_taught`, `last_taught`,
  `summary`, `lessons[]`) → **coverage map** + **lesson archive**.
- The current run's **scored mentions** (in memory during `main.py`) →
  **trending this week** + **gap highlights**. The dashboard build happens at the
  end of a run, so `main.py` passes `scored` + the chosen skill straight in.
- On a quiet day (no new items / no scored list), the page still rebuilds from
  memory alone (coverage + archive); trending/gaps sections show "no fresh data".

## Sections (single page, inline CSS, no JS framework, no deps)

1. **Trending skills this week** — top scored skills (skill, score, demand,
   sources), today's pick highlighted.
2. **Your coverage map** — skills from memory: name, times taught, last taught,
   current difficulty.
3. **Gap highlights** — scored skills with multi-source demand that are NOT in
   memory yet (the unmet gaps).
4. **Lesson archive** — every past lesson: date, skill, difficulty, summary.

## API

```python
# builder.py
build(memory: dict, scored: list[dict] | None = None,
      today_skill: str | None = None, out_path: Path = OUTPUT) -> Path
```

Pure render helpers per section (`_trending_html`, `_coverage_html`,
`_gaps_html`, `_archive_html`) assembled into one document by a small
`_page(title, body)` shell. `out_path` is a parameter so tests write to tmp.

`main.py`: after delivery/persist, call `dashboard.build(memory, scored, skill)`.
Wrap in try/except like delivery — a dashboard failure must not fail the run.

## Decisions (see question)

- **Audio in the archive** and **how the page is published** — these change scope
  and repo footprint; asked before implementing. Defaults below pending sign-off:
  - Archive is **metadata-only** (no embedded MP3 players) — MP3s aren't committed.
  - Publish via **`actions/deploy-pages`** artifact (no generated HTML committed
    to the repo); needs Pages enabled in repo settings (your action).

## Workflow

Add a Pages deploy to CI/cron: upload `dashboard/` as a Pages artifact and
`deploy-pages` after a successful run. (Exact mechanism depends on the publish
decision.)

## Testing (offline)

- `dashboard/tests`: `build()` with synthetic memory + scored → assert
  `index.html` written, contains each section heading, the chosen skill is
  marked, coverage rows render, gaps exclude already-taught skills, archive lists
  lessons. Empty memory + `scored=None` → still renders without crashing.
- HTML escaping of skill/summary text (skill names contain `<`, `&`, etc.).

## Decisions (signed off)

- **Embed audio players** in the archive — `<audio src="../output/lesson-*.mp3">`
  (resolves locally; Pages packaging of the MP3s deferred with publishing).
  `record_lesson` now stores the MP3 filename per lesson.
- **Build now, wire Pages later** — `build()` + `main.py` wiring + tests done; the
  Pages publish workflow is deferred until Pages is enabled in repo settings.

## Acceptance criteria — DONE (2026-05-30)

- [x] `build()` writes a self-contained HTML page (inline CSS, no deps) with all
      four sections from memory (+ optional scored data). Verified via a rendered
      sample (`output/sample-dashboard.html`).
- [x] Gap highlights exclude already-taught and table-stakes skills; trending
      marks today's pick (🎧). Archive is newest-first with audio players.
- [x] `main.py` regenerates the page each run (happy path + quiet-day paths),
      failure-isolated like delivery.
- [x] Offline tests pass — 40 total (4 new dashboard tests incl. HTML escaping);
      ruff clean.

## Out of scope

- Charts/JS interactivity (static lists/tables only for v1 of the dashboard).
- Hosting MP3s (unless the audio decision says otherwise).
