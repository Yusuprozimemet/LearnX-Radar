# v4 / Day 15 — Don't let a thin re-run clobber a rich dashboard

**Goal:** stop the trending board from flipping between "proper numbers" and
"every skill 0.50 from dev.to" depending on which run last wrote the state.

## Why it alternated

The dashboard rebuilds from committed `last_scored.json` / `trending_history.json`
(`pages.yml` → `builder.build_from_state()`), and those files are written from the
**post-dedup** ranking each run (`main()` scores `new_items`, not all scraped
items). The four sources refresh at very different rates:

- **dev.to** publishes new articles continuously → fresh items every run.
- **GitHub Trending / HN Hiring / Stack Overflow** use time-stable IDs → between
  their refreshes the same items come back already-seen and dedup drops them.

So the ranking is **run-dependent**:

- The first run of a period (or the first run right after the seen-set was reset)
  sees fresh trend items → a rich board (GitHub 1.0, multi-source 1.5…).
- A **same-day re-run** (manual `workflow_dispatch`) sees only new dev.to items →
  every skill at demand-weight 0.5 → an all-0.50 board.

And `save_trending_history` / `save_last_scored` **overwrote** unconditionally, so
a degraded re-run replaced the good morning board — even in the date-picker.

This is distinct from the day13 dedup window (which fixed the *permanent* drain so
trend sources recover after 14 days). The window can't help here: within 14 days a
same-day re-run still finds the trend items seen, so the run is genuinely thin.

## The fix (storage/state.py)

Keep scoring and teaching exactly as they are; only stop a weaker write:

- `_ranking_quality(scored) -> (top_score, distinct_sources, entry_count)` — a
  comparable richness, higher is richer. A dev.to-only run (top 0.5, one source)
  sorts below a multi-source run.
- `save_last_scored`: if the file already holds **today's** ranking and it is
  strictly richer than the incoming one, keep it (skip the write). A *new day*
  always writes — even a thin board — so the dashboard can never get stuck on a
  stale day.
- `save_trending_history`: same guard for the current day's entry.

Equal-quality writes still go through (a re-run can refresh same-richness data),
and a genuinely richer re-run replaces a thin earlier one.

## Scope / trade-off (chosen deliberately)

This is the "stop clobbering" option, not "make every board full." The board is
only ever as rich as the best run of the day; a pure dev.to re-run adds nothing
but no longer subtracts. The fuller alternative — score **all** scraped items for
the dashboard and keep dedup only for what gets taught — was considered and left
out to avoid changing teaching behavior (`extract` is a single batched LLM call,
so it stays cheap if revisited later).

Note: the board recovers on the next run that pulls fresh trend signal; it does
not retroactively fix an already-committed thin `last_scored.json`.

## Testing (offline)

- A thin same-day re-run does **not** clobber a rich `last_scored` / history.
- A richer re-run **does** replace a thin earlier one.
- A new day overwrites even with a thin board (no stale lock-in).

## Acceptance criteria

- [x] Same-day re-runs never downgrade the committed ranking.
- [x] A richer run always wins; a new day always writes.
- [x] Teaching, scoring, and the dedup window are unchanged.
- [x] Offline tests pass; ruff clean.

## Out of scope

- Scoring all items for the dashboard (the fuller fix) — deferred.
- De-duplicating the teaching path differently — unchanged here.
