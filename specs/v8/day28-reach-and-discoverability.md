# v8 / Day 28 — Reach & discoverability (dev.to + podcast directories + social card)

**Goal:** make the lesson *findable* beyond the people who already follow the
channel. Three additive levers, none of which stores PII or needs a server: a weekly
dev.to cross-post (SEO + a second audience), an Apple/Spotify-listable podcast feed
(not just generic RSS), and rich social-share previews for the dashboard.

---

## 1. Weekly dev.to cross-post

`delivery/devto_publisher.py` cross-posts the lesson **brief** to dev.to via the
Forem API — for reach and durable SEO that the ephemeral Telegram/podcast channels
don't give.

- **Weekly, not daily** (`DEVTO_POST_WEEKDAY`, Mon) — dev.to is a community platform;
  daily auto-posts would be spam.
- **Draft by default** (`DEVTO_PUBLISHED = False`) — review before it goes live.
- One authenticated `POST /api/articles`. Strips the brief's leading `# Title` (the
  API has its own title field) and appends a footer linking back to
  `t.me/learnradar`.
- `DEVTO_POST_TAGS` (≤4, lowercase per Forem rules).
- **Degrades to a no-op** when disabled, no `DEVTO_API_KEY`, missing brief, or wrong
  weekday. Wired into `main()` after delivery in its own `try/except`, so it never
  blocks the daily run.

```python
DEVTO_API_KEY            # dev.to -> Settings -> Extensions -> API Keys; unset -> skip
DEVTO_PUBLISH_ENABLED = True
DEVTO_POST_WEEKDAY = 0   # Mon (weekly)
DEVTO_PUBLISHED = False  # draft for review; True -> publish live
DEVTO_POST_TAGS = ["programming", "learning", "career"]
```

---

## 2. Apple/Spotify-compliant podcast feed

The v4 feed was valid RSS but missing the directory metadata Apple/Spotify require to
*list* a show. Extend `dashboard/feed.py`:

- Add the **iTunes namespace tags** (author, summary, category, explicit, type) and an
  `<itunes:owner>` with `PODCAST_OWNER_EMAIL` — Apple emails it to verify ownership.
- Reference square **cover art** ≥1400px (`PODCAST_IMAGE_URL` → `cover.png`);
  `pages.yml` copies it into the published site.
- **De-duplicate episodes by audio GUID** so a same-day re-run (or a duplicated Dutch
  record) never emits the same `<item>` twice.

Audio still hosted as **GitHub Release assets** (tag `lessons`), feed still served
from Pages — no new hosting, no credential beyond `GITHUB_TOKEN`. The show then lists
on **Spotify** and **Apple Podcasts**, not just generic RSS readers.

```python
PODCAST_IMAGE_URL    # square cover >=1400px (cover.png)
PODCAST_CATEGORY = "Technology"
PODCAST_OWNER_NAME
PODCAST_OWNER_EMAIL  # Apple ownership verification
```

---

## 3. Social-share preview (Open Graph / Twitter card)

A shared dashboard link should render a rich card, not a bare URL:

- The dashboard `<head>` gains **Open Graph** + **Twitter card** tags pointing at
  `OG_IMAGE_URL` (`og.png`, copied by `pages.yml`).
- A **"Join on Telegram"** CTA on the page links `CHANNEL_URL` (`t.me/learnradar`) — a
  plain constant (not the `TELEGRAM_CHANNEL_ID` secret) so the keyless Pages build can
  render it.

---

## Out of scope

- Publishing dev.to posts live automatically (kept manual via the draft default).
- Submitting the feed to directories programmatically (one-time manual submit).
- Any analytics that would track individual listeners/readers.
