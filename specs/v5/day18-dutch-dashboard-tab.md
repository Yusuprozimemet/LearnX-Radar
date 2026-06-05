# v5 / Day 18 — Dashboard Radar/Dutch tabs + Dutch podcast episodes

**Goal:** make the Dutch track *visible*. The static page gains a top **nav toggle**
between **Radar** (everything today) and **Dutch** (your Dutch progress), and the
Dutch lesson MP3s join the podcast feed. Built entirely from committed state
(`dutch_memory.json`) — the keyless Pages workflow renders it like everything else.

---

## Part A — Two tabs on one page (`dashboard/builder.py`)

The page renders all sections into one `body` (`builder.py:50`). Restructure into two
labelled groups and a nav that shows one at a time — same vanilla DOM technique the
date picker already uses (`builder.py:203`), no framework.

### Structure

```python
def build(memory, scored=None, today_skill=None, out_path=OUTPUT,
          history=None, dutch=None):           # NEW: dutch memory dict
    ...
    radar_body = "\n".join([_trending_html(history), _coverage_html(skills),
                            _gaps_html(scored, skills), _archive_html(skills)])
    dutch_body = _dutch_html(dutch or {})
    body = _tabs(radar_body, dutch_body)
```

`_tabs(radar, dutch)` wraps each in `<div id="tab-radar">` / `<div id="tab-dutch"`
(the latter `style="display:none"`) and emits the nav + a few lines of JS:

```html
<p class="nav tabs">
  <a href="#" data-tab="radar" class="active">📡 Radar</a>
  <a href="#" data-tab="dutch">🇳🇱 Dutch</a>
</p>
<script>
 // click a tab link -> show its div, hide the other, toggle .active
 // (vanilla, ~8 lines; mirrors the date-picker swap already in the page)
</script>
```

The existing `.nav` row (podcast feed + Releases links, `builder.py:329`) stays
visible above both tabs. Default view = Radar, so a returning visitor sees the radar
exactly as today.

### `build_from_state` (the keyless Pages path)

`build_from_state` (`builder.py:63`) loads committed state and renders. Add the Dutch
memory:

```python
return build(storage.load_memory(), state.get("scored", []),
             state.get("today_skill"), out_path,
             history=storage.load_trending_history(),
             dutch=storage.load_dutch_memory())     # NEW
```

`load_dutch_memory` already exists from day 17 and degrades to a default dict, so the
tab renders an empty state (not a crash) before any Dutch run has happened.

### `_dutch_html(dutch)` — the Dutch tab body

Four sections, all pure render from `dutch_memory.json` (no JS beyond the tab swap):

1. **🇳🇱 Progress** — CEFR level, current `streak`, total words introduced, and how
   many are scheduled for review today (`due <= today`). A compact stat row.
2. **🔁 Due for review** — the count + the next few due words (`nl` + `en`), so the
   learner sees what's resurfacing.
3. **🆕 Recent words** — a table of the most recently introduced words
   (`nl`, `en`, `pos`, `theme`, `reps`), newest first — the coverage analogue.
4. **🗂️ Dutch lesson archive** — cards from `dutch["lessons"]` (date · theme ·
   words · summary) with the **inline audio player**, reusing `_player(lesson)`
   (`builder.py:288`) so each Dutch MP3 streams from its Release asset exactly like a
   dev lesson. Empty state: "No Dutch lessons yet."

Reuse `_section`, `_esc`, table styling, and `_player` — no new CSS beyond a tiny
`.tabs a.active { font-weight:600 }` rule.

---

## Part B — Dutch episodes in the podcast feed (`dashboard/feed.py`)

`feed.py:_lessons` collects audio-bearing lessons from `skill_memory.json`
(`feed.py:39`). The Dutch lessons live in `dutch_memory.json["lessons"]` with the
same `date`/`audio`/`summary` shape, so fold them into the same item list.

```python
def _lessons(memory: dict, dutch: dict | None = None) -> list[dict]:
    items = [l for d in memory.get("skills", {}).values()
               for l in d.get("lessons", []) if l.get("audio")]
    if dutch:
        items += [{**l, "title": l.get("title") or f"Dutch — {l.get('theme','')} ({l.get('date','')})"}
                  for l in dutch.get("lessons", []) if l.get("audio")]
    items.sort(key=lambda l: l.get("date", ""), reverse=True)
    return items
```

`build_feed` / `build_feed_file` (`feed.py:67`, `feed.py:88`) take the Dutch memory
and pass it through:

```python
def build_feed(memory, dutch=None) -> str: ...
def build_feed_file(out_path=OUTPUT) -> Path:
    return ...build_feed(storage.load_memory(), storage.load_dutch_memory())
```

Dev and Dutch episodes interleave by date in one feed; the `guid` is the audio
filename (already unique: `lesson-*` vs `dutch-*`), so no collisions. One optional
nicety: prefix Dutch `<title>` with `🇳🇱` so they're scannable in a podcast app.

> Alternative considered: a separate `dutch.xml` feed. Rejected for now — one feed is
> simpler to subscribe to and the date-sorted mix reads naturally as "today's two
> lessons". Splitting later is a small change if wanted.

---

## What doesn't change

- The Radar tab is the current page verbatim (trending radar, coverage, gaps,
  archive, date picker) — just wrapped in a div and shown by default.
- No new dependencies, no JS framework, no backend, no API keys in the Pages job.
- `main.py` already calls `_refresh_dashboard`; the in-run `build()` can pass the
  live `dmem` so a local run shows the Dutch tab too (optional — the committed-state
  rebuild already covers Pages).

---

## Testing (offline)

- `_dutch_html`: with a sample Dutch memory, renders the progress stats, a due-words
  count matching `due <= today`, a recent-words table, and an archive card per lesson
  with a `<audio>` player for those having `audio`. Empty dict → empty-state copy, no
  crash.
- `_tabs`: emits both tab divs, the nav with two links, and the toggle script; Dutch
  div starts hidden; Radar content is present unchanged.
- `build` / `build_from_state`: accept and thread `dutch`; omitting it (old callers)
  still renders the Radar tab (back-compat).
- `feed.build_feed`: includes a Dutch lesson's `<item>` with its
  `RELEASES_AUDIO_BASE` enclosure URL; items are date-sorted across both sources;
  unique guids. With `dutch=None`, output equals the current dev-only feed
  (regression guard).

## Acceptance criteria

- [ ] The page has a 📡 Radar / 🇳🇱 Dutch top toggle; Radar is the default and is
      unchanged from today.
- [ ] The Dutch tab shows CEFR/streak/totals, due-for-review, recent words, and a
      Dutch lesson archive with working audio players — all from committed state.
- [ ] Dutch MP3s appear in `podcast.xml`, interleaved by date with dev lessons, with
      unique guids and Release-hosted enclosures.
- [ ] The keyless Pages workflow builds both with no new secrets; empty Dutch state
      renders cleanly before the first Dutch run.
- [ ] Offline tests pass; ruff clean.

## Out of scope

- CEFR auto-advance (A2→B1 as the learner's `reps`/streak grow), grammar drills, and
  any answer-checking/inbound loop — consistent with the project's no-inbound
  discipline; their own later spec if pursued.
