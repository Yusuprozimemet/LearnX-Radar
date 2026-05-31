# v4 / Day 13 — Time-windowed dedup (stop the ranking collapsing to one source)

**Goal:** keep the trend sources (GitHub Trending, HN Hiring, Stack Overflow)
feeding the radar run after run, instead of draining to dev.to-only within a
day or two. Fixes the symptom where the dashboard fills with skills all scoring
exactly `0.50` from a single source.

## The bug

`main()` runs `filter_new(items, seen)` **before** scoring, dropping every item
whose `id` is already in `seen_skills.json`. Three of the four sources use
**time-stable IDs** that reappear every run:

- GitHub Trending → `gh:{owner/repo}` (same repo, day after day)
- HN Hiring → `hn:{comment_id}` (same monthly thread's comments)
- Stack Overflow → `so:{tag}:{iso_week}` (same tag, same week)

With a permanent seen-set, the first run consumes them and every later run finds
them already seen → 0 new items. Only **dev.to** (unique per-article IDs, a feed
that refreshes constantly) keeps producing new items, so after a day or two it is
the *only* source left. Every surviving skill then has demand-weight `0.5`
(dev.to's weight) × novelty `1.0` = `0.50`, the ranking flattens, and there is
nothing to teach but dev.to buzz. (Pre-fix, the only workaround was a manual
`seen_skills.json` reset — see the historical `reset seen_skills dedup` commit.)

## The fix: a sighting expires

`seen_skills.json` changes from a **list of IDs** to a **map `id -> ISO date last
seen`**, and a sighting expires after `SEEN_TTL_DAYS` (default **14**). After the
window, a still-trending repo or still-hot tag re-enters as fresh demand signal.

Re-teaching the *same skill* is a **separate concern** already handled by
`gap_scorer` novelty (spaced repetition over `skill_memory.json`), so the seen
window only needs to stop re-processing the identical *source item* in
close-together runs — it can be short without risking duplicate lessons.

### `storage/state.py`

- `SEEN_TTL_DAYS = 14`, `_seen_cutoff()` → the ISO date before which a sighting is
  expired.
- `load_seen() -> dict[str, str]`. **Legacy migration:** a pre-window list-format
  file has no dates to window on, so it loads as an **empty map** — a safe one-time
  reset (novelty still prevents re-teaching; from the next run every ID carries a
  date). A corrupt/missing file also yields `{}`.
- `mark_seen(seen, ids, when=None)` stamps each id with `when` (default today),
  mutating in place. Only newly *processed* items are stamped; items filtered out
  as still-seen keep their original date, so **the window runs from first
  sighting** — a repo that keeps trending re-surfaces every `SEEN_TTL_DAYS`
  instead of being locked out (a sliding window would suppress it forever).
- `save_seen(seen)` drops entries past the TTL, then caps at the newest
  `MAX_SEEN` (still 5000), and writes the dict as indented JSON.
- `filter_new(items, seen)` returns items whose id is **not** seen within the
  window (`when >= cutoff`); expired ids fall through and get re-stamped today.

### `main.py`

`seen.update(item["id"] for item in new_items)` → `mark_seen(seen, (item["id"]
for item in new_items))`. The `load_seen → filter_new → … → mark_seen →
save_seen` flow is otherwise unchanged.

## Testing (offline)

- Legacy list-format file migrates to `{}` (one-time reset).
- `filter_new` suppresses a recent sighting but lets an expired one (and a
  brand-new id) through.
- `mark_seen` stamps today in place and leaves older entries untouched.
- `save_seen` prunes entries past the TTL.

## Acceptance criteria

- [x] `seen_skills.json` is a dated map; legacy lists migrate without crashing.
- [x] After the next run, GitHub Trending / HN Hiring / Stack Overflow contribute
      items again (verified: 59 / 100 / 5 against a migrated empty seen-set).
- [x] No skill is re-taught early — novelty still guards spaced repetition.
- [x] Offline tests pass; ruff clean.

## Out of scope

- Per-source TTLs (a single global window is enough; dev.to is naturally fresh and
  HN/SO/GitHub all benefit from the same 14-day recovery).
- Re-keying any agent's `id` scheme — the IDs stay stable on purpose; the window,
  not the key, is what lets a repeat re-surface.
