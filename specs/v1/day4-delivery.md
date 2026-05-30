# v1 / Day 4 — Delivery (lesson → Telegram + email)

**Goal:** deliver the finished MP3 lesson to Telegram and email. This is the last
v1 slice — after it, a `main.py` run actually *arrives* somewhere. Adapted from
Daily-CronJob (`delivery/`), changed from "send a text digest" to "send an audio
file + summary".

```
telegram_sender.send(lesson)   # uploads MP3 via sendAudio with a caption
email_sender.send(lesson)      # Gmail SMTP: HTML preview + MP3 attachment
```

Both channels are independent — `main.py` already wraps each in try/except, so
one failing never blocks the other.

## Lesson shape (from main.py, may be enriched here)

```python
{
  "title":    str,   # the skill, e.g. "Kafka consumer groups"
  "skill":    str,
  "summary":  str,   # one-line evidence/why-it-surfaced
  "difficulty": str, # beginner|intermediate|advanced  (add to lesson in main.py)
  "mp3_path": str,   # output/lesson-YYYYMMDD.mp3
  "brief_md": str,   # the full markdown teaching brief
}
```

## 1. `telegram_sender.py`

- `POST https://api.telegram.org/bot{token}/sendAudio` as multipart/form-data:
  - `audio` = the MP3 file handle (real upload, not a URL)
  - `chat_id`, `title` = lesson title, `performer` = "LearnX-Radar"
  - `caption` = built by a pure `_caption(lesson)` helper
- **Caption** (plain text, NO parse_mode — skill names contain arbitrary chars
  that would break Markdown): title line, the summary, and a short footer
  (`📡 LearnX-Radar · {difficulty} · {date}`). Capped at Telegram's 1024-char
  caption limit by the helper.
- `timeout=60` (file upload). Raise on non-200 so main.py logs it.

## 2. `email_sender.py`

- Gmail SMTP over SSL (port 465), same auth path as Daily-CronJob.
- `MIMEMultipart` with:
  - an HTML body from a pure `_render_html(lesson)` helper — title, difficulty,
    summary, and the brief (see decision below), styled simply like
    Daily-CronJob's cards.
  - the MP3 attached via `MIMEAudio` (filename `lesson-YYYYMMDD.mp3`).
- Subject: `LearnX-Radar — {title} ({Mon DD})`.

## Testing

- **Offline unit tests** (`delivery/tests/`, no network/SMTP):
  - `telegram._caption`: asserts title + summary present, plain text, length
    ≤ 1024 (feed an over-long summary → still capped).
  - `email._render_html`: asserts title/summary in the HTML; `_build_message`
    (factored pure) → assert subject, To/From, and that an audio attachment with
    the right filename is present. No real send.
- **Live (manual, creds are set):** run both `send()` on the existing
  `output/lesson-20260530.mp3`; confirm the audio + caption land in the Telegram
  chat and the email arrives with the MP3 attached and a readable body.

## Acceptance criteria — DONE (2026-05-30)

- [x] No stubs left in the pipeline — both senders implemented; `main.py`'s
      delivery loop calls them with the exact lesson dict shape that was
      live-tested. (Live send used `output/lesson-20260530.mp3`.)
- [x] Telegram: playable audio delivered with a clean plain-text caption
      (`[telegram] sent lesson 'DuckDB'`).
- [x] Email: arrived with the MP3 attached and the brief rendered as HTML notes
      (`[email] sent ... to yusuf.rozimemet@gmail.com`).
- [x] Offline unit tests pass — 5 delivery tests (caption cap, md→html render,
      HTML escaping, audio attachment present). 32 tests total across the project.

## Decisions (signed off)

- **Email body = full brief as readable notes.** Render `brief_md` to HTML with a
  small inline converter (headings/bullets/paragraphs) — no new dependency. MP3
  still attached.
- **`difficulty` added to the lesson dict** in `main.py` so both channels show it.
- **Caption** = title + summary + `📡 LearnX-Radar · {difficulty} · {date}` footer.
- Skipped: runner-up skills in the caption (needs threading the scored list
  through main.py for little gain).

After this slice, **v1 is feature-complete**; remaining work is the GitHub
Actions schedule (already drafted in `.github/workflows/radar.yml`) + a real run.
