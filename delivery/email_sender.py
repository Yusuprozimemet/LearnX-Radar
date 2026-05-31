"""Email the lesson: HTML notes (the full brief) + MP3 attachment.

Adapted from Daily-CronJob (delivery/email_sender.py): same Gmail SMTP (SSL)
path, but the body renders the whole teaching brief as readable notes and the
MP3 is attached, so the email doubles as written lesson notes.
"""
import html
import re
import smtplib
import ssl
from datetime import date
from email.mime.audio import MIMEAudio
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import config
from delivery import followup

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def _inline(text: str) -> str:
    """Escape HTML, then apply inline markdown (**bold**, `code`)."""
    text = html.escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    return text


def _markdown_to_html(md: str) -> str:
    """Small line-based markdown renderer — headings, bullets, code, paragraphs.

    Deliberately minimal (no dependency); the brief uses a known, simple subset.
    """
    out: list[str] = []
    in_list = False
    in_code = False
    code_buf: list[str] = []

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            out.append("</ul>")
            in_list = False

    for line in md.splitlines():
        fence = line.strip().startswith("```")
        if fence:
            if in_code:
                out.append(
                    "<pre style='background:#f6f8fa;padding:12px;border-radius:6px;"
                    "overflow:auto'><code>" + html.escape("\n".join(code_buf)) + "</code></pre>"
                )
                code_buf = []
            else:
                close_list()
            in_code = not in_code
            continue
        if in_code:
            code_buf.append(line)
            continue

        stripped = line.strip()
        if not stripped:
            close_list()
            continue
        if stripped.startswith("### "):
            close_list()
            out.append(f"<h3>{_inline(stripped[4:])}</h3>")
        elif stripped.startswith("## "):
            close_list()
            out.append(f"<h2>{_inline(stripped[3:])}</h2>")
        elif stripped.startswith("# "):
            close_list()
            out.append(f"<h1>{_inline(stripped[2:])}</h1>")
        elif stripped[:2] in ("- ", "* "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(stripped[2:])}</li>")
        else:
            close_list()
            out.append(f"<p>{_inline(stripped)}</p>")

    close_list()
    if in_code and code_buf:  # unclosed fence — flush what we have
        out.append("<pre><code>" + html.escape("\n".join(code_buf)) + "</code></pre>")
    return "\n".join(out)


_WRAP_STYLE = (
    "font-family:-apple-system,Segoe UI,Roboto,sans-serif;"
    "max-width:680px;margin:auto;line-height:1.5"
)


def _followup_button(lesson: dict) -> str:
    """An 'Ask on Perplexity' button linking to a thread seeded with the brief."""
    brief_file = lesson.get("brief_file")
    if not brief_file:
        return ""
    url = followup.perplexity_url(lesson["skill"], brief_file)
    style = (
        "background:#1f6feb;color:#fff;padding:10px 18px;"
        "border-radius:6px;text-decoration:none;display:inline-block"
    )
    return (
        f'<p style="margin:16px 0">'
        f'<a href="{url}" style="{style}">🔎 Ask follow-ups on Perplexity</a></p>'
    )


def _render_html(lesson: dict) -> str:
    return f"""
    <div style="{_WRAP_STYLE}">
      <p style="color:#888;font-size:13px;margin:0 0 4px">
        📡 LearnX-Radar · {lesson.get('difficulty', '')} · {date.today():%b %d, %Y}
      </p>
      <p style="color:#444">{_inline(lesson.get('summary', ''))}</p>
      <p style="color:#666;font-size:13px">🎧 Audio lesson attached below.</p>
      {_followup_button(lesson)}
      <hr style="border:none;border-top:1px solid #eee">
      {_markdown_to_html(lesson.get('brief_md', ''))}
    </div>"""


def _build_message(lesson: dict) -> MIMEMultipart:
    msg = MIMEMultipart()
    msg["Subject"] = f"LearnX-Radar — {lesson['title']} ({date.today():%b %d})"
    msg["From"] = config.EMAIL_FROM
    msg["To"] = config.EMAIL_TO
    msg.attach(MIMEText(_render_html(lesson), "html", "utf-8"))

    mp3 = Path(lesson["mp3_path"])
    audio = MIMEAudio(mp3.read_bytes(), _subtype="mpeg")
    audio.add_header("Content-Disposition", "attachment", filename=mp3.name)
    msg.attach(audio)
    return msg


def send(lesson: dict) -> None:
    """Email the lesson notes with the MP3 attached."""
    msg = _build_message(lesson)
    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(config.EMAIL_FROM, config.GMAIL_APP_PASSWORD)
        server.send_message(msg)
    print(f"[email] sent lesson '{lesson['title']}' to {config.EMAIL_TO}")
