# v4 / Day 15 — Score the full scrape so the dashboard always updates

**Goal:** the trending board should show proper numbers and update on **every**
run — not flip between a rich board and an all-0.50 dev.to wall depending on which
run last wrote the state.

## Root cause

`main()` scored only `new_items` (what survived dedup), and the dashboard rebuilds
from that committed ranking (`pages.yml` → `build_from_state()`). The sources
refresh at very different rates:

- **dev.to** publishes new articles continuously → fresh items every run.
- **GitHub Trending / HN Hiring / Stack Overflow** use time-stable IDs → between
  refreshes they come back already-seen and dedup drops them.

So a same-day re-run saw only new dev.to items → every skill at demand-weight 0.5
→ an all-0.50 board. The first attempt (a "don't let a thin re-run overwrite a
rich one" guard) only traded one complaint for another: the re-run was now
*skipped*, so the page didn't update at all.

## The fix (one real change)

Score the **whole scrape** for the dashboard, not just the post-dedup remainder:

```python
mentions = skill_extractor.extract(items)   # was: extract(new_items)
scored   = gap_scorer.score(mentions, memory, profile)
skill    = gap_scorer.top(scored)
```

`skill_extractor.extract` is a single batched LLM call regardless of item count,
so this is no more expensive. Now every run produces the full demand board and
writes it, so the page always reflects current signal and always updates.

Teaching is unaffected in practice: `gap_scorer` novelty already sinks
recently-taught skills toward 0, so `top(scored)` still picks a genuine gap — and
won't re-pick this morning's lesson on a same-day re-run.

Because the board can no longer go catastrophically thin, the day-15 "no-clobber"
guard (`_ranking_quality` in `save_last_scored` / `save_trending_history`) is
**removed** — the writes are unconditional again, which is what makes a re-run
update the page.

## What didn't change

- The dedup window (day13) and `seen_skills.json` still gate the *"is there
  anything new at all"* check and what counts as a fresh item for teaching.
- The follow-up/quiz deep links (day14) are untouched.

## Testing (offline)

- The removed no-clobber tests are dropped with the guard.
- Existing state tests (seen window, last_scored roundtrip/trim, history) still
  pass.

## Acceptance criteria

- [x] Every run writes the full-scrape ranking; the page updates each time.
- [x] The board shows multi-source scores again (not all 0.50) whenever the
      trend sources have signal.
- [x] No extra LLM cost (still one batched extract call).
- [x] Offline tests pass; ruff clean.

## Note

This supersedes the day-15 "no-clobber" guard, which was a band-aid for the thin
board rather than a fix for why the board was thin.
