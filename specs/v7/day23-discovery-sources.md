# v7 / Day 23 — Discovery Sources (accuracy)

**Goal:** widen the radar's input from 4 to 7 sources to raise *selection*
accuracy — i.e. how often the skill we pick is genuinely rising and worth
teaching. Today 3 of 4 sources (Stack Overflow, GitHub, dev.to) are
**vocabulary-locked** to hardcoded tag/language lists, so the radar can only
*track* a fixed watchlist; only HN Hiring can *discover* a skill we didn't
pre-list. This slice adds three **open-vocabulary** discovery feeds.

Add three agents:

| Agent | Signal | Vocabulary | Weight |
|---|---|---|---|
| `reddit_agent` | community demand / discovery | **open** | 0.75 |
| `hn_front_agent` | what devs are actually reading | **open** | 1.0 |
| `lobsters_agent` | curated high-signal discussion | **open** | 1.0 |

All three are zero-auth, **stateless**, and cron-safe (no cookies, no
datacenter-IP blocks — Reddit uses `.rss`, the lesson proven in
[[daily-cronjob-build]] and LearnX-Search).

This slice does **not** touch dev.to, GitHub Trending, or `gap_scorer` logic —
those are separate follow-ups (see *Out of scope*).

> **Note on the trade-off:** the originally-proposed PyPI adoption agent (a
> real-*usage* magnitude signal) was **dropped** by decision — its watchlist was
> too specific to be worth the stateful complexity. So this slice delivers the
> bigger accuracy lever (open-vocabulary discovery) but leaves the pipeline with
> no real-adoption/download signal; everything stays discussion/buzz-based.

---

## Shared contract (unchanged — `agents/__init__.py`)

Every `fetch()` returns `list[dict]`, each item with all six keys:

```python
{"id": str, "source": str, "title": str, "url": str, "text": str, "meta": str}
```

Rules (same as Day 1):
- A network/parse failure may raise — `main._scrape` already catches per-source.
- Within an agent, a single bad row is skipped, not fatal.
- `requests` uses `config.USER_AGENT` and `timeout=20`.
- **`text` is the field the `skill_extractor` reads** — note the copied
  Daily-CronJob reddit agent uses `desc`; we rename it to `text` here.

Endpoint shapes below are stated from the known public APIs; per project
discipline each is **verified live once** during implementation before the parse
is finalized (mirrors the Day 1 spec). Reddit `.rss` is already proven (runs
unattended in Daily-CronJob's Actions cron).

---

## 1. `reddit_agent.py`  (open-vocabulary discovery)

Copy the structure of `Daily-CronJob/agents/reddit_agent.py` (Atom parse via
`xml.etree` + `BeautifulSoup` content strip), adapting to Radar's config + the
`text` key.

- **URL:** `https://www.reddit.com/r/{sub}/top.rss?t=week&limit={limit}` for each
  `config.REDDIT_SUBREDDITS`. **Weekly** (`t=week`), not daily — a daily window
  is too volatile for a *skill* trend; weekly is steadier signal.
- **Parse:** Atom `<entry>`; `<id>` is `t3_<postid>` → keep `<postid>`;
  `<link href>`; `<content>` HTML → strip to plain text (cap ~300 chars).
- **Item mapping:**
  - `id` = `rd:{postid}` (post identity → a post hot all week dedups to one)
  - `source` = `"Reddit"`
  - `title` = entry `<title>`
  - `url` = entry link href
  - `text` = stripped content (the post body/preview — where skill names appear)
  - `meta` = `f"reddit · r/{sub}"`
- **UA:** Reddit 429s the default urllib UA → must send `config.USER_AGENT`
  (descriptive). `.rss` returns 200 from datacenter IPs where `.json` 403s.
- **Dep:** `requests`, `bs4` (both already in requirements).

## 2. `hn_front_agent.py`  (open-vocabulary discovery)

- **URL:** `https://hn.algolia.com/api/v1/search?tags=front_page` → `hits` is the
  current front page (~30 stories). (Same Algolia API the hiring agent uses.)
- **Item mapping (one item per story):**
  - `id` = `hnfp:{objectID}`
  - `source` = `"HN Front Page"`
  - `title` = hit `title`
  - `url` = hit `url` (external link) or the HN item URL if `url` is null
    (Ask/Show HN have no external url).
  - `text` = `title` (+ `hit["story_text"]` when present, stripped). The title is
    the primary signal; we deliberately do **not** fetch the linked article
    (latency/privacy — that's the synthesis/enrichment job, not discovery).
  - `meta` = `f"hn · {points} pts"`
- **Edge:** skip hits with no title.
- **Dep:** `requests` (no new dep).

## 3. `lobsters_agent.py`  (curated high-signal discovery)

- **URL:** `https://lobste.rs/rss` (the hottest stories; higher signal/noise than
  dev.to). Optionally per-tag `https://lobste.rs/t/{tag}.rss` later.
- **Parse:** `feedparser.parse(...)`; take first `config.LOBSTERS_LIMIT` entries.
- **Item mapping:**
  - `id` = `lob:{entry.link}` (story URL identity)
  - `source` = `"Lobste.rs"`
  - `title` = `entry.title`
  - `url` = `entry.link`
  - `text` = stripped `entry.summary` + any tag terms appended (tags carry the
    topic, e.g. `rust`, `ai`, `databases`)
  - `meta` = `"lobste.rs"`
- **Dep:** `feedparser` (already in requirements).

---

## Config additions (`config.py`, in the "Data sources" block)

```python
# Reddit — open-vocabulary discovery via public weekly RSS (no auth; .rss, not .json).
# Lanes: AI, software dev, full-stack, frontend, backend (API/DB/devops),
# python, java, typescript, plus SaaS/startup for product & market-trend signal.
# Tune freely — these are the discovery surface, not a fixed answer.
REDDIT_SUBREDDITS = [
    "artificial",       # AI
    "ExperiencedDevs",  # software development (high-signal)
    "webdev",           # full stack
    "Frontend",         # frontend
    "devops",           # backend — CI/CD, infra, deployment
    "Database",         # backend — database integration / data layer
    "Python",           # python
    "java",             # java
    "typescript",       # typescript
    "SaaS",             # SaaS — what people are building/selling
    "startups",         # startups — product & market trends
]
REDDIT_LIMIT = 15  # top posts per subreddit per week

# Hacker News front page (Algolia) — what devs are reading right now.
# (no extra config; ~30 stories returned)

# Lobste.rs — curated, higher signal/noise than dev.to.
LOBSTERS_LIMIT = 25
```

### Source weights (`config.SOURCE_WEIGHTS`)

Slot the new sources into the existing weight ladder (real demand > buzz). Add:

```python
"Lobste.rs": 1.0,     # curated discussion, high signal/noise
"HN Front Page": 1.0, # broad dev attention
"Reddit": 0.75,       # community discovery, noisier than HN/Lobsters
```

(HN Hiring 2.0 / SO 1.5 / GitHub 1.0 / dev.to 0.5 unchanged.) `gap_scorer` needs
**no code change** — `_demand_weight` already sums `SOURCE_WEIGHTS` over the
distinct sources mentioning a skill; unlisted sources fall back to
`DEFAULT_SOURCE_WEIGHT`, but we set explicit weights so the ladder is deliberate.

---

## `main.py` wiring

1. **Imports:** add `hn_front_agent, lobsters_agent, reddit_agent` to the
   `from agents import (...)` block.
2. **`_scrape` no-arg tuple:** add `reddit`, `hn_front`, `lobsters` to
   `no_arg_sources` (they take no args, just like github/hn/devto). No stateful
   wiring needed — none of the three reads prior state.
3. **Privacy `known_sources` set** (`_scrape`, ~line 81): add the three new source
   names — `"Reddit", "HN Front Page", "Lobste.rs"` — so they get the normal
   title/text/meta scrub rather than the generic all-string-fields scrub.

No other stage changes — `skill_extractor`, `gap_scorer`, dashboard, delivery,
and storage all flow through unchanged.

---

## Testing

- Offline **parse tests** in `agents/tests/` — one fixture per source
  (saved RSS/Atom/JSON), one test asserting the six-key contract + key fields:
  - reddit: Atom entry → `rd:` id + `text` populated.
  - hn_front: front_page hit → `hnfp:` id; Ask/Show HN (null `url`) falls back to
    the HN item URL.
  - lobsters: RSS entry → `lob:` id + tags appended to `text`.
- Each agent gets a `if __name__ == "__main__":` smoke-run guard (UTF-8 stdout
  reconfigure, like the existing agents) for live eyeballing.
- Run pytest **scoped to Radar pkg dirs** (agents radar learnx delivery storage
  dashboard dutch) — root `pytest` sweeps sibling LearnX-CLI tests that fail on
  missing fixtures (known gotcha).

## Acceptance criteria

- [ ] `python main.py` prints non-zero fetched counts for the three new sources
      alongside the existing four, then proceeds normally.
- [ ] Every new item satisfies the six-key contract.
- [ ] A live run surfaces at least one skill whose `sources` includes a new
      source (proves discovery widened, not just re-weighted).
- [ ] Parse tests pass offline against fixtures; `ruff` clean.

## Out of scope (separate follow-ups)

- **PyPI / npm adoption agents** — dropped from this slice (watchlist too
  specific to justify the stateful complexity). Revisit only if a real-*usage*
  magnitude signal is later wanted; PyPI would mirror the `stackoverflow_agent`
  prior-count pattern, npm a copy of that.
- **Drop/replace dev.to** (weight 0.5, SEO-spam, tag-locked) — decide after we
  see how the three new discovery feeds perform.
- **GitHub Trending fixes** — `since=weekly` (steadier) + feed the scraped
  `stars_today` magnitude into demand weight (currently parsed then discarded).
- **Lesson-content grounding** — bolt LearnX-Search's `gather → synthesize` after
  the skill is picked to ground the brief in fresh cited sources. That fixes
  *content* accuracy; this slice fixes *selection* accuracy. (See [[learnx-search-build]].)
```