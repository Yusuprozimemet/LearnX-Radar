# v1 / Day 1 — Data Collection Agents

**Goal:** make all four `agents/*.py` `fetch()` functions return real, normalized
items from live endpoints. No API keys required for any of them. This is the
input layer of the radar — everything downstream consumes its output.

Endpoint shapes below are **verified live** (2026-05-30), not assumed.

---

## Shared contract (already defined in `agents/__init__.py`)

Every `fetch()` returns `list[dict]`, each item:

```python
{
    "id":     str,   # stable, unique — drives dedup in storage.seen_skills
    "source": str,   # "GitHub Trending" | "HN Hiring" | "dev.to" | "Stack Overflow"
    "title":  str,
    "url":    str,
    "text":   str,   # free text the skill_extractor reads (may be "")
    "meta":   str,   # short human context line
}
```

Rules for all agents:
- Network/parse failure raises (orchestrator in `main.py` catches per-source).
- Within an agent, a single bad row is skipped, not fatal.
- `requests` uses `config.USER_AGENT` and `timeout=20`.

---

## 1. `github_trending_agent.py`

- **URL:** `https://github.com/trending/{language}?since={since}` for each
  `config.TRENDING_LANGUAGES`, `since=config.TRENDING_SINCE`.
- **Parse (BeautifulSoup, `html.parser`):** each repo is `article.Box-row`.
  - name → `h2.h3 a` → href is `/owner/repo`; strip to `owner/repo`.
  - description → the `p` inside the row (may be absent → `""`).
  - stars-today → the `span` containing text like "123 stars today" (may be absent).
- **Item mapping:**
  - `id` = `gh:{owner/repo}` (repo identity, not date — a repo trending two days
    running is the *same* learnable thing; dedup should suppress the repeat).
  - `title` = `owner/repo`
  - `url` = `https://github.com/{owner/repo}`
  - `text` = description
  - `meta` = `f"{language} · {stars_today}"`
- **Dep:** `beautifulsoup4` (in requirements).

## 2. `hn_hiring_agent.py`

- **Find thread:** `GET https://hn.algolia.com/api/v1/search_by_date`
  `?tags=story,author_whoishiring&query=hiring&hitsPerPage=1`
  → newest hit's `objectID` is the current monthly thread.
  (Verified: filtering by `author_whoishiring` returns the real
  "Ask HN: Who is hiring? (May 2026)" thread, 555 comments — the naive query
  without the author tag returns the wrong story.)
- **Pull comments:** `GET https://hn.algolia.com/api/v1/items/{objectID}`
  → `children` is the list of top-level comments; take up to
  `config.HN_HIRING_LIMIT`. Each child: `{id, text (HTML), author}`.
- **Item mapping (one item per comment = one job post):**
  - `id` = `hn:{comment_id}`
  - `source` = `"HN Hiring"`
  - `title` = first line of stripped text, truncated ~80 chars
  - `url` = `https://news.ycombinator.com/item?id={comment_id}`
  - `text` = comment text, HTML stripped (employer language = best skill signal)
  - `meta` = `f"hiring · {month_year_from_thread_title}"`
- **Edge cases:** skip children with no `text` (deleted/empty).
- **Dep:** stdlib `html`/regex for tag stripping (no new dep).

## 3. `devto_agent.py`

- **URL:** `https://dev.to/feed/tag/{tag}` for each `config.DEVTO_TAGS`.
- **Parse:** `feedparser.parse(...)`; take first `config.DEVTO_LIMIT` entries.
  - `entry.title`, `entry.link`, `entry.summary` (HTML), `entry.tags`
    (list of `{term}` → maps from `<category>`, verified present).
- **Item mapping:**
  - `id` = `devto:{entry.link}`
  - `title` = `entry.title`
  - `url` = `entry.link`
  - `text` = stripped `entry.summary` + tag terms appended
  - `meta` = `f"dev.to · {tag}"`
- **Spam filter (required):** dev.to tag feeds contain SEO spam (verified: top
  "ai" item was "Buy Verified Wise Accounts"). Drop entries whose title matches
  an obvious-spam pattern (e.g. `buy|verified accounts|cheap|\bSMM\b`,
  case-insensitive). Keep the filter list small and documented.
- **Dep:** `feedparser` (in requirements).

## 4. `stackoverflow_agent.py`

- **URL:** `https://api.stackexchange.com/2.3/questions`
  `?site=stackoverflow&tagged={tag}&filter=total&pagesize=1`
  → returns `{"total": N}` (verified) = current recent-question volume for the tag.
- **Delta:** compare `N` against the previous reading stored under
  `skill_memory["so_counts"][tag]`. This agent **reads** prior state but does not
  write it — persistence stays in `main.py`/storage to keep the agent pure.
  - For Day 1, if no prior reading exists, emit the item with `delta=None`
    (first run is a baseline, not a signal).
- **Item mapping (one item per *rising* tag):**
  - `id` = `so:{tag}:{iso_week}` (one signal per tag per week)
  - `title` = `f"{tag} questions rising"`
  - `url` = `https://stackoverflow.com/questions/tagged/{tag}`
  - `text` = `f"Stack Overflow questions tagged {tag}: {N} (Δ {delta})"`
  - `meta` = `f"stackoverflow · Δ{delta}"`
- **Open question for review:** the delta needs a prior count. Options:
  (a) store `so_counts` in `skill_memory.json` (simplest, one file), or
  (b) a dedicated `storage/so_counts.json`. **Recommend (a).** Flag for sign-off
  because it touches the storage schema.

---

## Testing

- Each agent gets a `if __name__ == "__main__": print(fetch())` guard so it can
  be smoke-run standalone: `python -m agents.devto_agent`.
- Add `agents/tests/` (pytest) with **parse tests** over saved HTML/JSON/RSS
  fixtures (no live network in CI) — mirrors LearnX-CLI's test discipline.
  - One fixture per source, one test asserting item shape + key fields.
- Manual acceptance: run each agent once live, eyeball that items look real.

## Acceptance criteria — DONE (2026-05-30)

- [x] `python main.py` (with dummy keys) prints non-zero fetched counts for all
      four sources (57 / 100 / 40 / 5 = 202 items), then proceeds to the radar
      stage (which still stubs out — clean halt at the Day 1 boundary).
- [x] Every returned item satisfies the shared contract (all six keys present).
- [x] dev.to spam entries are filtered out (tightened: "verified <service>
      accounts" with a word between, e.g. "Verified Binance Accounts").
- [x] HN agent resolves the correct current "Who is hiring?" thread via
      `author_whoishiring` (May 2026, 100 job posts).
- [x] Parse tests pass offline against fixtures (6 passed).

**Resolved during build:** `so_counts` stored in `skill_memory.json` (signed
off); SO agent reads prior counts, `main.py` persists new ones even on a quiet
day so the baseline survives. `__main__` demos reconfigure stdout to UTF-8 for
the Windows cp1252 console.

## Out of scope (later days)

- Skill extraction / scoring / brief (Day 2–3).
- Writing `so_counts` back to memory — wired in `main.py` on the storage day.
- RemoteOK RSS source (plan lists it; defer unless a source is too thin).
