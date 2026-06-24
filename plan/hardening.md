# Hardening plan — make LearnX-Radar read as production-grade

**Goal:** turn the "Unknown" rows on a portfolio review (production-scale,
backend depth, DevOps) into visible "yes" — using *this one* system instead of
starting new repos. Most of the work is making strength that already exists
legible to someone who only sees the GitHub page.

**What's already here (don't rebuild):** CI lint+test, per-stage failure guards
in `main.py`, a failure-report DM, `storage/run_history.py` + Status tab, PII
scrub. The gap is *depth + proof*, not absence.

Do these in order. Each step ends with a written artifact, because the writeup
*is* the evidence.

---

## 1. Observability you can point at  (highest leverage)
The Status tab already records per-run health. Push it from "did it run" to
"how is it behaving over time."

- [ ] Add timing per stage (scrape / extract / score / brief / audio / deliver),
      not just total `duration_s`. Store in the run entry; render as a small
      trend on the Status tab.
- [ ] Add a tiny `OBSERVABILITY.md`: what each metric means, where it's stored,
      how to read the dashboard. One screenshot.

## 2. One real load/throughput test  (flips "production-scale: Unknown")
- [ ] Pick the heaviest path (scrape + extract). Write `scripts/loadtest.py`
      that runs it against N× the normal item volume.
- [ ] Record the result in `docs/LOAD.md`: "at Nx items, stage X is the
      bottleneck (p99 = Y s), fixed/mitigated by Z." A short honest table beats
      a perfect number.

## 3. One documented data/storage optimization  (backend depth signal)
State is JSON files that grow daily — that *is* a real scaling concern (the
parked rotation idea). Turn it into a documented fix.

- [ ] Show the problem: size/load-time of a state file as it grows (a quick
      measurement).
- [ ] Apply one fix: bounded rotation / compaction / lazy load. Capture
      before/after load time in the same doc. (Ties into the parked
      state-retention idea — this is the moment to land a slice of it.)

## 4. Failure-mode robustness  (reliability signal)
Guards keep the run alive; add one real recovery path and name it.

- [ ] Add retry-with-backoff on the flakiest external call (an agent fetch or
      the LLM call). The breaker state already exists — document it as the
      circuit breaker it is.
- [ ] Make `record_lesson` / state writes idempotent for a re-run on the same
      day (so a retried cron can't double-write). One test proving it.

## 5. DevOps polish  (cheap, high visual impact)
- [ ] Add CI status badge to the README.
- [ ] Add a `Dockerfile` + one-command `docker run` that does a dry run from a
      clean clone. Document the single command in the README.
- [ ] Note the GitHub Actions cron schedule in the README as "the deploy" —
      it already is one; make it legible.

---

## Order of attack
1 → 5 → 2 → 4 → 3. (Observability + badges/Docker are fast wins and make
everything else visible; load test and storage opt are the deeper proofs.)

## Out of scope
- No new projects. Depth on this one is the whole point.
- No "org leadership"/Staff signal — wrong target for a solo build.