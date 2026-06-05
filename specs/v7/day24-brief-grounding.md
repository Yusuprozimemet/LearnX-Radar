# v7 / Day 24 — Brief grounding (content accuracy)

**Goal:** stop writing the lesson brief from the model's memory. Today
[`brief_writer.write`](../../radar/brief_writer.py) builds the brief from only the
skill name + a 15-word `evidence` string + the source *names* — it never reads the
actual material the radar collected. So Day 23 raised **selection** accuracy
(picking a genuinely rising skill); this slice raises **content** accuracy:
ground the brief in the real text of the sources that surfaced the skill, plus
optional fresh web results, with inline `[n]` citations.

This is the "Lesson-content grounding" follow-up parked in
[day23-discovery-sources.md](day23-discovery-sources.md) *Out of scope*. It is
**Phase 1** of the retrieval roadmap (Phase 2 = map-reduce extraction; Phase 3 =
vector DB for cross-day trends — both out of scope here).

It works by **vendoring a minimal subset of LearnX-Search** (`gather → read →
synthesize`) into Radar — the Item contract is already identical between the two
projects ([learnx_search/models.py](../../../LearnX-Search/learnx_search/models.py)).

---

## Locked design decisions

1. **Keep Radar's `brief.txt` structure — do NOT adopt LearnX-Search's layered
   format.** The audio pipeline parses `## Do this in 5 minutes` out of the brief
   via [`brief_writer.action_step`](../../radar/brief_writer.py), and
   curriculum/dialogue depend on the current sections. We reuse Search's
   *machinery* (read URLs → numbered cited context → one synthesis call) but feed
   it through Radar's existing prompt + sections. Replacing the prompt would
   silently break audio.
2. **Reuse by copy (vendoring), not import.** Both projects ship a top-level
   `config.py` and separate `learnx` / `learnx_search` packages, so a clean
   cross-import is impossible (config collision). Vendor a small subset into a new
   `radar/research/` package, rewired to Radar's `config` + `learnx.llm`. Header
   each copied file with its source path for future manual sync. (Matches the
   ecosystem's established reuse-by-copy pattern.)
3. **Exa is wired in.** A free `EXA_API_KEY` is available. The keyless Jina reader
   (full-reads of URLs the radar *already has*) is the spine; Exa adds fresh,
   beyond-corpus web results. Exa degrades gracefully — absent key → empty results,
   run continues (existing channel behavior).
4. **The read budget N is NOT asserted — it is determined by experiment.** How
   many sources to *fully read* per brief is a quality vs. latency trade-off, so a
   guessed constant is not acceptable. N is a tunable config knob, and this slice
   ships an experiment harness that measures quality + latency across N values; the
   chosen N is recorded from data (see *Experiment* below).

---

## New package: `radar/research/` (vendored from LearnX-Search)

All four files keep the shared six-key Item contract
(`{id, source, title, url, text, meta}`) and rewire `import config` →
Radar's config and the LLM call → `learnx.llm.chat`.

| File | Source | Role |
|---|---|---|
| `base.py` | `channels/base.py` | `Channel` ABC (minimal — just what web/exa need) |
| `web.py` | `channels/web.py` | **keyless** Jina Reader (`r.jina.ai`); `read(url) -> Item\|None`. Returns None on blocked/errored/empty pages so we never cite a dead read. Keeps the GH-calendar + Jina-warning scrubbing. |
| `exa.py` | `channels/exa.py` | Exa neural search; `search(query, limit) -> list[Item]`. Returns `[]` without `EXA_API_KEY`. |
| `synth.py` | `channels/../synthesis.py` (subset) | `filter_relevant(query, items, keep, min_terms)` (pure lexical ranking, no LLM) + `_format_context(items, text_chars)` (numbered `[n]` source blocks). **No** `synthesize`/router/other channels copied — Radar's `brief_writer` owns the prompt. |

> Not copied: `router.py` (we already know the skill *and* its URLs — no routing
> needed), `synthesize` (Radar keeps its own prompt), and the
> youtube/twitter/v2ex/reddit/rss channels (out of scope for grounding).

> **Exa `limit<1` guard (impl. note):** `exa.search` returns `[]` when
> `limit < 1` — Exa's API rejects `numResults=0` with HTTP 400. The experiment
> sweeps N (including N=0), and `brief_writer` calls `exa.search(limit=N)`, so
> without the guard the N=0 cell errors. Harmless (caught + logged), but the guard
> keeps the ungrounded baseline clean.

---

## Grounding pipeline (inside `brief_writer.write`)

`write` gains the day's scraped `items` so it can select grounding sources. New
signature: `write(skill: dict, memory: dict, items: list[dict], chat_fn=chat)`.

```
chosen skill X
  1. CANDIDATES
     a. day's own items mentioning X  → research.filter_relevant(X, items)
     b. if EXA_API_KEY:  research.exa.search(X)   → fresh beyond-corpus sources
     dedup by url/id, rank by relevance, take top GROUNDING_CANDIDATES
  2. READ
     full-read the top GROUNDING_READ_TOP_N candidate URLs via research.web.read
     (Jina, keyless, per-read timeout, failure-isolated). Remaining candidates
     keep their snippet/Exa-highlight text. privacy.scrub() every fetched body.
  3. CONTEXT
     research._format_context(selected, text_chars=GROUNDING_TEXT_CHARS)
     → numbered "[n] Source — Title \n URL \n text" blocks
  4. SYNTHESIZE
     one chat() call through Radar's brief.txt (now with a {grounding} block +
     "cite as [n]"), keeping ALL existing sections.
```

**Failure isolation / fallback:** if there are no items for the skill, or every
read fails, fall back to the current ungrounded brief (skill + evidence) so the
daily run never dies for lack of grounding. A grounded brief is an upgrade, never
a hard dependency.

**Privacy:** full-page reads are *new external text* that bypassed Radar's
ingestion-time scrub in `_scrape`. Run `privacy.scrub` on every fetched body
before it reaches the prompt, dedup, or delivery.

---

## Prompt change: `radar/prompts/brief.txt`

Add a `{grounding}` block (the numbered source context) and a citation
instruction, **without changing any section heading**:

- Insert after `SEEN IN: {sources}`:
  ```
  GROUNDING SOURCES (cite inline as [n] using these numbers):
  {grounding}
  ```
- Amend `## Why it's on the radar today` and `## Core ideas` to "cite the
  grounding sources inline as [n] where a claim rests on one." When `{grounding}`
  is empty (fallback path) the instruction is harmless — the model simply has
  nothing to cite.
- All five headings (`Why it's on the radar today`, `What you'll learn`, `Core
  ideas`, `Where it fits`, `Do this in 5 minutes`) stay byte-for-byte so
  `action_step` + curriculum keep working.

### Citations are authored from data, not written by the LLM (impl. refinement)

The `## Sources` list is **appended deterministically in `brief_writer`** from the
real selected URLs — the model is told NOT to write a Sources list or any URL, only
to emit inline `[n]` markers. Rationale: LLMs reliably fabricate plausible-but-fake
source URLs, so the reference list must be authored from data, never generated.
`_select_sources` returns the chosen items in `[n]` order; `format_context` numbers
them identically for the prompt, so the model's inline `[n]` align with the appended
list. The appended `## Sources` heading also correctly bounds `action_step` (it
stops at the next `^#+\s` heading). When there is no grounding, no Sources section is
appended and the model is instructed to use no `[n]` markers.

---

## Config additions (`config.py`)

```python
# --- Exa web search (Phase 1 brief grounding) — free key at https://exa.ai.
# Absent -> Exa search yields nothing and grounding falls back to the day's own
# source URLs (read keylessly via Jina). The run never fails for a missing key.
EXA_API_KEY = os.getenv("EXA_API_KEY")

# --- Brief grounding (v7 Day 24) ---
GROUNDING_ENABLED = True        # master switch; False = legacy ungrounded brief
GROUNDING_CANDIDATES = 12       # candidates ranked before deciding what to read
GROUNDING_READ_TOP_N = 5        # PROVISIONAL — confirmed by the experiment below
GROUNDING_TEXT_CHARS = 1500     # per-source cap fed into the brief prompt
GROUNDING_HTTP_TIMEOUT_S = 20   # per Jina/Exa request
```

`GROUNDING_READ_TOP_N = 5` is a **placeholder pending the experiment** — the spec
is not done until the value is set from measured data and this comment updated.

---

## Experiment: choosing `GROUNDING_READ_TOP_N` from data

A guessed N is rejected by project principle — measure it. Ship a one-off harness
(`scripts/exp_grounding.py`, deletable; not part of the cron path):

- **Input:** a handful of real chosen skills (reuse a saved scored run / today's
  `output/` dump, or 3–4 hand-picked skills spanning lanes: one AI, one
  frontend, one backend/infra).
- **Sweep:** for `N ∈ {0, 2, 3, 5, 8}` (N=0 = today's ungrounded baseline), run
  the full grounding + brief for each skill.
- **Measure & record** to `output/exp_grounding/`:
  | metric | how |
  |---|---|
  | reads attempted / succeeded | count (Jina drops blocked pages) |
  | per-read latency | wall-clock per `web.read` |
  | total brief-stage latency | wall-clock for the whole `write` |
  | context size | tokens fed to the synthesis call |
  | brief quality | the briefs written side-by-side for human read |
- **Decision rule:** pick the **smallest N where brief quality plateaus** while
  total brief-stage latency stays inside the cron budget (target: brief stage
  **< ~90s**, since the daily Actions run also does audio + Dutch + delivery).
  More reads ≠ better past the point where the synthesis call already has enough
  grounded material; we want the knee of the curve, not the max.
- **Output of the experiment:** set `GROUNDING_READ_TOP_N` to the chosen value and
  update its config comment + this section with the measured table and the
  one-line rationale.

### Result (run 2026-06-05, 3 skills: DuckDB, Agentic coding, Kafka consumer groups)

Averaged over the 3 skills (full per-cell table in
`output/exp_grounding/summary.md`):

| N | avg ctx tokens | avg read latency | citations | notes |
|---|---|---|---|---|
| 0 | 0 | 0s | none | ungrounded baseline |
| 2 | 823 | ~7s | thin (1–2 sources, sometimes uncited) | |
| 3 | 1222 | ~5s | all 3 cited, brief stable (~550w) | **quality plateau** |
| 5 | 2026 | ~8s | 4 of 5 cited | plateau + headroom |
| 8 | 3203 | ~14s | 5 of 8 cited; brief got *shorter* (391w) | wasteful |

> **Caveat:** the brief-stage *LLM* latency was unusable as a signal this run — the
> NIM free tier had a timeout storm (10 retries; some cells 200–360s of pure
> backoff). That latency is **N-independent** (one brief call regardless of N), so
> the decision rests on the N-controlled signals: read latency (small, ≤~14s even
> at N=8) and context size (linear in N). On a normal day the brief LLM call is
> ~6s, so brief-stage stays well under the 90s budget at any tested N.

**Chosen: `GROUNDING_READ_TOP_N = 5`.** Quality plateaus at N=3 (stable length, all
sources cited, canonical docs surfaced by Exa). N=8 is rejected — the model ignores
~3 of 8 sources, the brief gets shorter, and context grows 60% for no gain. 5 = the
N=3 plateau plus headroom for the blocked/empty Jina reads that occur in production
(this run got an optimistic 15/15 successful reads); at N=5 a couple of failures
still leave 3–4 usable sources. Token/latency cost of 5 over 3 is negligible
(~800 tokens, ~3s). Leaner alternative if token budget ever matters: N=3.

---

## `main.py` wiring

- [main.py:213](../../main.py) `brief = brief_writer.write(skill, memory)` →
  `brief_writer.write(skill, memory, items)` (pass the day's scraped items so the
  grounder can select + read). No other stage changes — curriculum, dialogue,
  audio, delivery, storage all consume the brief markdown unchanged.

---

## Testing

Offline, no network (monkeypatch `research.web.read`, `research.exa.search`, and
`chat_fn`):

- **Grounded path:** prompt handed to `chat_fn` contains the numbered grounding
  block with real URLs + the `[n]` instruction; the returned brief still passes
  `action_step` (i.e. `## Do this in 5 minutes` survives).
- **Fallback path:** with empty items / all reads returning None, `write` still
  produces a valid brief (legacy ungrounded) and never raises.
- **Privacy:** a fetched body containing an email/handle is scrubbed before it
  appears in the prompt context.
- **Vendored parse tests:** `web._clean` (Jina header/boilerplate strip) and
  `exa.search` (no key → `[]`; with mocked response → well-formed Items) — reuse
  or adapt the LearnX-Search fixtures.
- Run pytest **scoped to Radar pkg dirs** (agents radar learnx delivery storage
  dashboard dutch research) — root `pytest` sweeps sibling LearnX-CLI tests that
  fail on missing fixtures (known gotcha). `ruff` clean.

## Acceptance criteria

- [ ] A brief for a real chosen skill cites `[n]` sources that resolve to actual
      URLs from the day's corpus and/or Exa.
- [ ] `action_step` still extracts the 5-minute exercise (format preserved); the
      audio pipeline is unaffected.
- [ ] Run with `EXA_API_KEY` **absent** still produces a grounded brief from the
      day's own URLs (Jina-only); run with no usable sources falls back cleanly.
- [ ] Every fetched body is privacy-scrubbed before synthesis/delivery.
- [ ] The experiment table is produced and `GROUNDING_READ_TOP_N` is set from it
      (not a guess), with the rationale recorded.
- [ ] Offline tests pass; `ruff` clean.

## Out of scope (later phases of the retrieval roadmap)

- **Phase 2 — map-reduce extraction.** The 429-item digest is analyzed in one LLM
  pass (≤20 skills out); chunk + extract + deterministic source counting would fix
  recall/attribution. Separate slice.
- **Phase 3 — vector DB (embedded, e.g. LanceDB / sqlite-vss).** Cross-day
  *semantic* trend tracking ("rising over two weeks") and semantic dedup that
  id-matching can't do. Embeddings can ride the existing NIM key. The only place a
  persistent store is the right tool.
- **Router + remaining channels** (youtube/twitter/v2ex/reddit/rss search) — not
  needed to ground a known skill from known URLs.
```
