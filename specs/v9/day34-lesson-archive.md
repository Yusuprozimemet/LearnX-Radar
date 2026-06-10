# v9 / Day 34 — Lesson archive (reopen any past day)

**Goal:** the trainer shows the latest lesson only — `dutch_lesson.json` is
overwritten every run, so yesterday's lesson vanishes from the site the moment
today's lands (Day 32 explicitly deferred the back-catalog). Keep every day's
lesson and let the learner reopen it from the trainer's lesson list — a
finished lesson stays visitable. Same architecture as everything
else: the daily run commits state, Pages serves it, the browser does the rest.

---

## 1. The archive — written by the daily run

`save_dutch_lesson` keeps writing `dutch_lesson.json` (the page's default view)
and now also writes:

- `storage/lessons/dutch-<YYYY-MM-DD>.json` — a dated copy of the full payload.
- `storage/lessons/index.json` — the manifest the page's lesson list renders:
  `{"lessons": [{"date", "theme", "cefr"}, ...]}`, sorted by date. A same-day
  re-run replaces that day's entry instead of duplicating it.

The radar workflow commits `storage/lessons/`; the Pages deploy copies it to
`_site/lessons/`. The archive grows from the day this ships — earlier lessons
were overwritten and survive as audio only (releases + podcast feed).

## 2. The lesson list — the 🏆 lessen tab grows reopen buttons

The lessen tab already lists per-day scores from `localStorage`; it now merges
in the manifest's dates, so a day appears even if it was never trained on this
device. Each archived day that isn't currently open gets a ▶ button: fetch
`lessons/dutch-<date>.json`, render it as the current lesson (leren step 1,
like a fresh open), highlight its row. Today's row keeps its "vandaag" badge.

Scores, the 3-attempt exam limit, and the one-chance luistertoets listens are
already keyed by date in `localStorage` — reopening a past day shows its real
state and does **not** grant fresh exam attempts. The leren steps (listening,
imitating, reading along) are always re-doable; that's the point of reopening.

## 3. Audio for archived days

The Pages deploy keeps a same-origin MP3 copy (`dutch_audio.mp3`) for the
*latest* lesson only — copying every day's audio would grow the site by ~1 MB/day
for no reason. Archived days play their `audio_url` straight from the release
CDN: the CDN sends no CORS header (so the blob trick is unavailable) but honours
Range requests, so `currentTime` seeking — sentence-by-sentence play — still
works. Slightly slower first seek; everything else identical.

---

## Out of scope

- Retro-filling the pre-archive days (audio-only; not worth synthesizing JSON).
- Pruning the archive (a year is ~365 × ~10 KB JSON — negligible).
- A calendar/date-picker UI (the lessen list *is* the picker).
- Cross-device progress sync (still localStorage only).
