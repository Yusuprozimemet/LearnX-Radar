# v10 / Day 38 — Private state repo + LLM resilience (keep personal data off the public repo, stop a slow NVIDIA from timing out the run)

**Goal:** this is a public portfolio repo, but the daily run committed **personal
state** straight into it — Dutch SR memory (CEFR, streak, every word + review
schedule), the lesson archive, the curated word bank, and radar state. All of it
was browsable in the public tree and git history. Move it out so nothing personal
lives in the public repo, while the public dashboard + podcast keep rendering it.
Separately, a recurring operational failure: a *degraded-slow* (not dead) NVIDIA
recovers within retries so the existing Groq fallback never engages, yet each
timeout burns ~120s and the accumulated waiting blows the job's 20-min cap before
any call exhausts its retries — observed live (5 timeouts, ~10 min wasted, Groq
never reached, job cancelled mid-run). Fix both, deterministically and reversibly.

This pairs with [[day37-backlog-backpressure]] in spirit: small, guarded, config-
or env-driven changes that never touch the dev pipeline's correctness.

---

## 1. State lives in a private repo, resolved via `STATE_DIR`

A second repo, **`LearnX-Radar-state`** (private), holds the per-user state. The
app resolves its data directory from the `STATE_DIR` env var, defaulting to the
local `storage/` folder — so local runs and tests are unchanged, and CI points
`STATE_DIR` at a checkout of the private repo.

- `storage/state.py` introduces `_DATA_DIR = Path(os.environ.get("STATE_DIR", _DIR))`
  and routes every data-file constant through it (`_DIR` stays the code dir).
  `dutch/coach.py` and `scripts/curate_aliases.py` (which built log paths off
  `_DIR`) switch to `_DATA_DIR`.
- The Dutch **word bank** moves too: `dutch/wordlist.py` resolves `STATE_DIR` at
  call time, with the bundled `wordlist.json` as a local fallback.
- **What stays public:** `briefs/` (lessons link to them by raw URL) and all
  application code.

### Files moved to the private repo
`seen_skills.json`, `skill_memory.json`, `last_scored.json`, `trending_history.json`,
`skill_aliases.json`, `skill_aliases_denylist.json`, `skill_aliases_log.md`,
`dutch_memory.json`, `dutch_lesson.json`, `dutch_coach_log.md`, `lessons/` (dated
archive + `index.json`), and `wordlist.json`.

### Workflows
A `STATE_REPO_TOKEN` secret (fine-grained PAT, Contents R/W on the state repo)
authorizes the private checkout in each workflow (`path: state`, `STATE_DIR` set to
it). No other workflow logic changes because the path resolution is centralized:

- **radar.yml** — commits `briefs/` to the public repo, pushes all state to the
  private repo (on `always()`, so already-folded feedback survives a failed run).
- **pages.yml** — read-only private checkout; the dashboard + podcast feed render
  from it. Public site output is unchanged.
- **curate.yml** — pushes learned aliases to the private repo.

### Important limitation (by design)
Privatizing the file hides the **raw data and git history**, not the **rendered
page**: the public dashboard still renders Dutch stats/words (it reads the private
state at build time). True hiding of the rendered surface is a later "login" phase;
this slice is the storage foundation for it. Public `main` history was scrubbed of
the moved files (`git-filter-repo` + force-push); older branches and immutable PR
refs were intentionally left. Lesson **audio** on public Releases also stays public.

---

## 2. NVIDIA circuit breaker (learnx/llm.py)

The fallback was per-call: NVIDIA gets `_RETRY_COUNT` attempts (each `_TIMEOUT_S`)
and only a *fully* failed NVIDIA call falls to Groq. That protects against a **dead**
NVIDIA, not a **slow** one. Add a per-run breaker:

- Count NVIDIA `APITimeoutError`s across the run. After `_NVIDIA_TRIP_AFTER` (2),
  **trip**: drop NVIDIA from `_providers()` and serve every remaining call from
  Groq directly. The trip also abandons NVIDIA mid-call (it doesn't wait out the
  last retry).
- Only trips when Groq is configured (no fallback ⇒ NVIDIA-only behaviour, and the
  full retry budget, are unchanged).
- State is process-global, so it resets each run (one `python main.py`);
  `reset_breaker()` exists for tests.

**Effect:** worst-case NVIDIA waiting drops from "however many calls × ~120s" to
~2 timeouts before the run switches entirely to fast Groq — comfortably inside the
20-min cap. Validated live: the next radar run completed in 7m14s.

---

## 3. Tests

- `learnx/tests/test_llm.py` (new): breaker trips after 2 timeouts and routes to
  Groq with NVIDIA never retried again; the no-Groq-key path keeps the full NVIDIA
  retry budget and never trips.
- Existing suite unchanged: `STATE_DIR` defaults to `storage/`, so all 220 tests
  pass without modification.

---

## 4. Multi-user note

This is the concrete foundation for personalized lessons: the public repo is the
engine + (optional) default word bank; each learner supplies their own private
state repo (their `STATE_DIR`), holding exactly the files in §1. No engine change
needed beyond the path resolution shipped here.