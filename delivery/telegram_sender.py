"""Send the lesson MP3 + summary to Telegram via sendAudio.

Adapted from Daily-CronJob (delivery/telegram_sender.py): instead of a text
digest we upload the audio file with the skill summary as a caption.

Caption is plain text (no parse_mode) on purpose — skill names contain arbitrary
characters (C#, `await`, etc.) that would break Markdown parsing.
"""
from datetime import date
from pathlib import Path

import requests

import config

SEND_AUDIO = "https://api.telegram.org/bot{token}/sendAudio"
CAPTION_LIMIT = 1024  # Telegram caption max length


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


def send(lesson: dict) -> None:
    """Upload lesson['mp3_path'] with a caption to the configured chat."""
    mp3 = Path(lesson["mp3_path"])
    with mp3.open("rb") as audio:
        resp = requests.post(
            SEND_AUDIO.format(token=config.TELEGRAM_BOT_TOKEN),
            data={
                "chat_id": config.TELEGRAM_CHAT_ID,
                "caption": _caption(lesson),
                "title": lesson["title"],
                "performer": "LearnX-Radar",
            },
            files={"audio": (mp3.name, audio, "audio/mpeg")},
            timeout=60,
        )
    resp.raise_for_status()
    print(f"[telegram] sent lesson '{lesson['title']}'")
