"""Send the lesson MP3 + summary to Telegram via sendAudio.

Adapted from Daily-CronJob (delivery/telegram_sender.py): instead of a text
digest we upload the audio file with the skill summary as a caption.

Caption is plain text (no parse_mode) on purpose — skill names contain arbitrary
characters (C#, `await`, etc.) that would break Markdown parsing.
"""
import json
import re
from datetime import date
from pathlib import Path

import requests

import config
from delivery import followup

SEND_AUDIO = "https://api.telegram.org/bot{token}/sendAudio"
SEND_MESSAGE = "https://api.telegram.org/bot{token}/sendMessage"
CAPTION_LIMIT = 1024  # Telegram caption max length
MESSAGE_LIMIT = 4096  # Telegram text-message max length


def _caption(lesson: dict) -> str:
    title = lesson["title"]
    summary = lesson.get("summary", "")
    footer = f"📡 LearnX-Radar · {lesson.get('difficulty', '')} · {date.today():%b %d, %Y}"
    body = f"🎧 {title}\n\n{summary}\n\n{footer}".strip()
    if len(body) <= CAPTION_LIMIT:
        return body
    # Trim the summary (the only long part) to fit, keeping title + footer.
    keep = CAPTION_LIMIT - len(f"🎧 {title}\n\n\n\n{footer}") - 1
    trimmed = summary[: max(0, keep)].rstrip() + "…"
    return f"🎧 {title}\n\n{trimmed}\n\n{footer}"


def _reply_markup(lesson: dict) -> dict:
    """Inline keyboard: a follow-up button (today's brief) and, when a previous
    lesson exists, a recall-quiz button (the prior lesson's brief). Both deep
    links embed the brief *text* so Perplexity has grounding without scraping."""
    rows = []
    brief_md = lesson.get("brief_md")
    skill = lesson.get("skill")
    if brief_md and skill:
        rows.append([{
            "text": "🔎 Ask follow-ups on Perplexity",
            "url": followup.perplexity_url(skill, brief_md),
        }])
    quiz_brief = lesson.get("quiz_brief_md")
    quiz_skill = lesson.get("quiz_skill")
    if quiz_brief and quiz_skill:
        rows.append([{
            "text": "🧠 Quiz me on this",
            "url": followup.quiz_url(quiz_skill, quiz_brief),
        }])
    if not rows:
        return {}
    return {"reply_markup": json.dumps({"inline_keyboard": rows})}


def _dutch_html(md: str, limit: int) -> str:
    """Convert the Dutch lesson markdown to Telegram HTML (sent with parse_mode=HTML):
    **Dutch** -> <b> (bold), _English_ -> <i> (italic), headings -> bold, bullets ->
    '• '. Telegram has no text colour, so bold/italic is how Dutch and English are
    distinguished. Trimmed to `limit` at a LINE boundary so no HTML tag is ever cut
    mid-way (which Telegram would reject)."""
    if len(md) > limit - 80:
        kept: list[str] = []
        total = 0
        for line in md.splitlines():
            if total + len(line) + 1 > limit - 80:
                break
            kept.append(line)
            total += len(line) + 1
        md = "\n".join(kept)
    # Escape HTML specials first; our markdown markers (**, _, #) aren't specials.
    esc = md.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    esc = re.sub(r"^\s*#{1,6}\s*(.+)$", r"<b>\1</b>", esc, flags=re.MULTILINE)  # heading -> bold
    esc = re.sub(r"^\s*[-*]\s+", "• ", esc, flags=re.MULTILINE)                 # bullets
    esc = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)                           # **bold**
    esc = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", esc)                    # _italic_
    return esc.strip()


def _dutch_reply_markup(dutch: dict) -> dict:
    words = dutch.get("quiz_words") or []
    if not words:
        return {}
    button = {"text": "🇳🇱 Quiz me in Dutch", "url": followup.dutch_quiz_url(words)}
    return {"reply_markup": json.dumps({"inline_keyboard": [[button]]})}


def _send_dutch(lesson: dict) -> None:
    """Deliver the Dutch lesson (v5) as its own message: a second sendAudio when a
    Dutch MP3 exists, else a plain text sendMessage. No-op when the run produced no
    Dutch lesson, so dev-only delivery is unchanged."""
    dutch = lesson.get("dutch") or {}
    if not dutch.get("markdown"):
        return
    token = config.TELEGRAM_BOT_TOKEN
    markup = _dutch_reply_markup(dutch)
    mp3 = dutch.get("mp3_path")
    if mp3 and Path(mp3).exists():
        path = Path(mp3)
        with path.open("rb") as audio:
            resp = requests.post(
                SEND_AUDIO.format(token=token),
                data={
                    "chat_id": config.TELEGRAM_CHAT_ID,
                    "caption": _dutch_html(dutch["markdown"], CAPTION_LIMIT),
                    "parse_mode": "HTML",
                    "title": "Dutch lesson",
                    "performer": "LearnX-Radar",
                    **markup,
                },
                files={"audio": (path.name, audio, "audio/mpeg")},
                timeout=60,
            )
    else:
        resp = requests.post(
            SEND_MESSAGE.format(token=token),
            data={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "text": _dutch_html(dutch["markdown"], MESSAGE_LIMIT),
                "parse_mode": "HTML",
                **markup,
            },
            timeout=60,
        )
    resp.raise_for_status()
    print("[telegram] sent Dutch lesson")


def send(lesson: dict) -> None:
    """Upload lesson['mp3_path'] with a caption to the configured chat, then send the
    Dutch lesson (when present) as a separate message."""
    mp3 = Path(lesson["mp3_path"])
    with mp3.open("rb") as audio:
        resp = requests.post(
            SEND_AUDIO.format(token=config.TELEGRAM_BOT_TOKEN),
            data={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "caption": _caption(lesson),
                "title": lesson["title"],
                "performer": "LearnX-Radar",
                **_reply_markup(lesson),
            },
            files={"audio": (mp3.name, audio, "audio/mpeg")},
            timeout=60,
        )
    resp.raise_for_status()
    print(f"[telegram] sent lesson '{lesson['title']}'")
    _send_dutch(lesson)
