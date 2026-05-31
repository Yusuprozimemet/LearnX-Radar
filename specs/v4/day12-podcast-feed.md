# v4 / Day 12 — Podcast feed (lessons in your podcast app)

**Goal:** route the MP3 the pipeline already generates into a real podcast app
(Pocket Casts, Apple Podcasts, AntennaPod) so the daily lesson is there for the
commute — without breaking the free-tier, no-external-credentials discipline.

## Hosting decision: GitHub Releases (not Pages, repo, or GCS)

A podcast `<enclosure>` needs the MP3 at a stable public URL. Options weighed:

| Option | Verdict |
|---|---|
| Commit MP3 into repo | ✗ unbounded git-history growth (~5 MB/day forever) |
| GitHub Pages | ✗ published-site capped ~1 GB → full in ~6 months; this is why the dashboard is metadata-only |
| **GitHub Releases** | ✓ asset/file up to 2 GB, **not** counted in git history, stable `…/releases/download/<tag>/<file>` URL, **needs no new credential** (workflow `GITHUB_TOKEN`) |
| Google Cloud Storage | ✗ for now — free tier works (5 GB) but requires a billing account + service-account key as a secret; over-built for a 5 MB/day file |

A 5-min edge-tts MP3 is ~2–5 MB; Releases handle this indefinitely. Public audio
is acceptable for a personal learning feed (if private audio is ever needed, that
pushes back toward GCS signed URLs — out of scope).

## Upload (`.github/workflows/radar.yml`)

After `python main.py`, before/after the state commit, upload the day's MP3 as a
Release asset under a single rolling tag (e.g. `lessons`), creating it once:

```yaml
- name: Publish lesson audio
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: |
    f=$(ls output/lesson-*.mp3 2>/dev/null | tail -1) || exit 0
    [ -z "$f" ] && exit 0   # quiet day: no lesson, nothing to publish
    gh release view lessons >/dev/null 2>&1 || gh release create lessons -t "LearnX-Radar lessons" -n "Daily lesson audio"
    gh release upload lessons "$f" --clobber
```

The asset download URL is then deterministic:
`https://github.com/<owner>/LearnX-Radar/releases/download/lessons/lesson-YYYYMMDD.mp3`.
Add `RELEASES_AUDIO_BASE` to `config.py` next to `BRIEFS_RAW_BASE`.

## Feed builder (`feed.py` or `dashboard/feed.py`)

Pure render, no LLM, no new dependency (hand-write the RSS XML like the dashboard
hand-writes HTML):

- `build_feed(memory) -> str` reads `skill_memory.json` lessons (each already has
  `date`, `title`, `audio` filename, `summary`) and emits an RSS 2.0 document with
  the iTunes namespace.
- One `<item>` per lesson: `<title>`, `<description>` (summary), `<pubDate>`,
  `<guid>` (the audio filename), and `<enclosure url=… type="audio/mpeg"
  length=…/>` where `url = RELEASES_AUDIO_BASE + "/" + lesson["audio"]`.
- Skip lessons whose `audio` is empty.
- Write `podcast.xml` next to `dashboard/index.html` so the **existing Pages
  workflow publishes it** with no change (the feed XML is tiny — no space concern).

`length` (bytes): use the local MP3 size during an in-run build; for the Pages
rebuild-from-state path the file isn't present, so `length` is optional in RSS —
omit it when unknown, or persist the byte size in `record_lesson` if a client
demands it (verify against a real client first; most accept a missing/0 length).

## Subscribing

The feed URL is the Pages-published `…github.io/LearnX-Radar/podcast.xml`. Add it
to a podcast app via "add by URL". Document this in the README.

## Testing (offline)

- `build_feed` with a 2-lesson memory emits valid RSS: one `<channel>`, two
  `<item>`s, each `<enclosure>` URL = `RELEASES_AUDIO_BASE/<audio>`,
  `type="audio/mpeg"`.
- Lessons with empty `audio` are skipped.
- Empty memory → a valid empty `<channel>` (no crash).
- XML-escapes titles/summaries (skill names like `C#`, `await`).

## Acceptance criteria

- [ ] Radar workflow uploads each day's MP3 to the `lessons` Release (no-op on a
      quiet day with no lesson).
- [ ] `podcast.xml` is generated from committed state and published via Pages.
- [ ] Subscribing to the feed URL in a podcast client plays the daily lessons.
- [ ] `config.py` has `RELEASES_AUDIO_BASE`; README documents the feed URL.
- [ ] Offline tests pass; ruff clean.

## Out of scope

- Private/authenticated audio (would require GCS signed URLs).
- Cover art / rich iTunes channel metadata beyond what a client needs to subscribe
  (can be added later as static channel fields).
- Pruning old Release assets (the rolling tag accumulates; revisit if it ever
  approaches the 2 GB asset ceiling — years away at 5 MB/day).
