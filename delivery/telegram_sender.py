"""Send the lesson MP3 + summary (+ full-lesson PDF) to Telegram.

Adapted from Daily-CronJob: instead of a text digest we upload the audio file
with the skill summary as a caption, plus the full brief as a PDF document
(captions cap at 1024 chars). Delivery fans out to every target in `_targets()`
— the owner's chat and, when configured, a public broadcast **channel**
(`TELEGRAM_CHANNEL_ID`) so anyone who joins the channel gets the lessons. The
channel holds the subscriber list, so we store no personal data ourselves.
"""
import json
import re
from datetime import date
from pathlib import Path

import requests

import config
from delivery import followup, pdf

SEND_AUDIO = "https://api.telegram.org/bot{token}/sendAudio"
SEND_MESSAGE = "https://api.telegram.org/bot{token}/sendMessage"
SEND_DOCUMENT = "https://api.telegram.org/bot{token}/sendDocument"
CAPTION_LIMIT = 1024  # Telegram caption max length
MESSAGE_LIMIT = 4096  # Telegram text-message max length

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"


def _check(resp: requests.Response) -> None:
    """Raise on a non-2xx Telegram response, surfacing Telegram's JSON `description`.

    requests' own raise_for_status hides the body, so a frozen bot or a missing
    admin right shows only "400 Bad Request" in the logs — useless for diagnosis.
    Telegram puts the real reason (e.g. "PEER_ID_INVALID", "FROZEN_METHOD_INVALID")
    in `description`; we fold it into the error so failures are self-explanatory.
    """
    if resp.ok:
        return
    try:
        detail = resp.json().get("description", "")
    except ValueError:
        detail = resp.text[:300]
    raise requests.HTTPError(f"{resp.status_code} {detail}".strip(), response=resp)


def _targets() -> list[str]:
    """Distinct chat ids to deliver to: the owner chat + the broadcast channel.

    TELEGRAM_CHANNEL_ID is optional; when set (and the bot is an admin there),
    lessons are posted to the channel so its members all receive them.
    """
    ids: list[str] = []
    for cid in (config.TELEGRAM_CHAT_ID, getattr(config, "TELEGRAM_CHANNEL_ID", None)):
        if cid and cid not in ids:
            ids.append(cid)
    return ids


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "lesson"


def _token_for(chat_id: str) -> str:
    """Use the dedicated channel-bot token for the channel target (if configured),
    else the main bot token. Lets a separate public bot own the channel."""
    channel = getattr(config, "TELEGRAM_CHANNEL_ID", None)
    channel_token = getattr(config, "TELEGRAM_CHANNEL_BOT_TOKEN", None)
    if channel and chat_id == channel and channel_token:
        return channel_token
    return config.TELEGRAM_BOT_TOKEN


def _send_document(chat_id: str, path: Path, caption: str, token: str,
                   markup: dict | None = None) -> None:
    """Upload a PDF (full lesson) via sendDocument — sidesteps the 1024 caption cap."""
    with Path(path).open("rb") as doc:
        resp = requests.post(
            SEND_DOCUMENT.format(token=token),
            data={
                "chat_id": chat_id,
                "caption": caption[:CAPTION_LIMIT],
                "parse_mode": "HTML",
                **(markup or {}),
            },
            files={"document": (Path(path).name, doc, "application/pdf")},
            timeout=120,
        )
    _check(resp)


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


def _rating_row() -> list[dict]:
    """Five star buttons deep-linking the day's lesson rating back to the bot
    (t.me/<bot>?start=lr_<YYMMDD>_<n>) — the dev track's quality signal, riding
    the same getUpdates loop as the Dutch trainer's recall reports. Empty when
    the feature is off or the bot's public username isn't configured."""
    if not (config.LESSON_RATING_ENABLED and config.TELEGRAM_BOT_USERNAME):
        return []
    base = f"https://t.me/{config.TELEGRAM_BOT_USERNAME}?start=lr_{date.today():%y%m%d}"
    return [{"text": "⭐" * n, "url": f"{base}_{n}"} for n in range(1, 6)]


def _reply_markup(lesson: dict, rate: bool = False) -> dict:
    """Inline keyboard: a follow-up button (today's brief) and, when a previous
    lesson exists, a recall-quiz button (the prior lesson's brief). Both deep
    links embed the brief *text* so Perplexity has grounding without scraping.
    `rate` adds the star-rating row — owner DM only (ratings from other chats
    would be ignored by the ingestion, so the channel never sees dead buttons)."""
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
    if rate:
        if stars := _rating_row():
            rows.append(stars)
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
    rows = []
    # Delft trainer (v9 day 32): tap-to-play sentences, checked cloze, enforced
    # one-chance listening — the interactive half of the lesson.
    if config.DUTCH_TRAINER_ENABLED:
        rows.append([{"text": "🎧 Train this lesson (Delft)", "url": config.TRAINER_URL}])
    words = dutch.get("quiz_words") or []
    if words:
        rows.append([{"text": "🇳🇱 Quiz me in Dutch", "url": followup.dutch_quiz_url(words)}])
    if not rows:
        return {}
    return {"reply_markup": json.dumps({"inline_keyboard": rows})}


def _send_dutch(chat_id: str, lesson: dict, dutch_pdf: Path | None, token: str) -> None:
    """Deliver the Dutch lesson to one chat: audio (teaser caption) + full PDF, or a
    text message when there's no audio. No-op when the run produced no Dutch lesson."""
    dutch = lesson.get("dutch") or {}
    md = dutch.get("markdown")
    if not md:
        return
    markup = _dutch_reply_markup(dutch)
    mp3 = dutch.get("mp3_path")
    has_audio = bool(mp3 and Path(mp3).exists())
    pdf_on = config.TELEGRAM_PDF_ENABLED and dutch_pdf is not None
    # With a full PDF attached, the audio caption is only a teaser; otherwise it
    # carries as much of the lesson as the 1024 cap allows.
    caption = _dutch_html(md, 600 if pdf_on else CAPTION_LIMIT)

    if has_audio:
        with Path(mp3).open("rb") as audio:
            _check(requests.post(
                SEND_AUDIO.format(token=token),
                data={
                    "chat_id": chat_id, "caption": caption, "parse_mode": "HTML",
                    "title": "Dutch lesson", "performer": "LearnX-Radar", **markup,
                },
                files={"audio": (Path(mp3).name, audio, "audio/mpeg")},
                timeout=60,
            ))
    elif not pdf_on:
        _check(requests.post(
            SEND_MESSAGE.format(token=token),
            data={"chat_id": chat_id, "text": _dutch_html(md, MESSAGE_LIMIT),
                  "parse_mode": "HTML", **markup},
            timeout=60,
        ))

    if pdf_on:
        # Quiz button rides the audio when present; else attach it to the PDF.
        _send_document(chat_id, dutch_pdf, "🇳🇱 <b>Dutch lesson</b> — full text",
                       token, markup={} if has_audio else markup)
    print(f"[telegram] sent Dutch lesson -> {chat_id}")


def _render_pdfs(lesson: dict) -> tuple[Path | None, Path | None]:
    """Render the dev + Dutch lesson PDFs once (reused across all targets)."""
    brief_pdf = dutch_pdf = None
    if not config.TELEGRAM_PDF_ENABLED:
        return brief_pdf, dutch_pdf
    if lesson.get("brief_md"):
        try:
            out = OUTPUT_DIR / f"lesson-{date.today():%Y%m%d}-{_slug(lesson['title'])}.pdf"
            brief_pdf = pdf.render_pdf(lesson["brief_md"], lesson["title"], out,
                                       footer=f"📡 LearnX-Radar · {lesson['title']}")
        except Exception as exc:
            print(f"[telegram] lesson PDF render failed (non-fatal): {exc}")
    dmd = (lesson.get("dutch") or {}).get("markdown")
    if dmd:
        try:
            out = OUTPUT_DIR / f"dutch-{date.today():%Y%m%d}.pdf"
            dutch_pdf = pdf.render_pdf(dmd, "Dutch lesson", out,
                                       footer="🇳🇱 LearnX-Radar · Dutch")
        except Exception as exc:
            print(f"[telegram] Dutch PDF render failed (non-fatal): {exc}")
    return brief_pdf, dutch_pdf


def _deliver_one(chat_id: str, lesson: dict, brief_pdf: Path | None,
                 dutch_pdf: Path | None) -> None:
    """Send the full lesson bundle (dev audio + PDF, Dutch audio + PDF) to one chat."""
    token = _token_for(chat_id)
    is_owner = str(chat_id) == str(config.TELEGRAM_CHAT_ID)
    mp3 = Path(lesson["mp3_path"])
    with mp3.open("rb") as audio:
        _check(requests.post(
            SEND_AUDIO.format(token=token),
            data={
                "chat_id": chat_id, "caption": _caption(lesson),
                "title": lesson["title"], "performer": "LearnX-Radar",
                **_reply_markup(lesson, rate=is_owner),
            },
            files={"audio": (mp3.name, audio, "audio/mpeg")},
            timeout=60,
        ))
    if brief_pdf is not None:
        _send_document(chat_id, brief_pdf, f"📄 <b>{lesson['title']}</b> — full lesson",
                       token, markup=_reply_markup(lesson))
    print(f"[telegram] sent lesson '{lesson['title']}' -> {chat_id}")
    _send_dutch(chat_id, lesson, dutch_pdf, token)


def post_waitlist(force: bool = False, chat_id: str | None = None) -> bool:
    """Post the personalization-waitlist CTA to the channel — a recurring upsell.

    Piggybacks the daily cron: posts only on config.WAITLIST_POST_WEEKDAY unless
    `force`. `chat_id` overrides the target (used to preview privately). Returns
    True if a message was sent. No data is collected here — the CTA links to a
    hosted form that holds responses.
    """
    if not config.WAITLIST_ENABLED:
        return False
    target = chat_id or getattr(config, "TELEGRAM_CHANNEL_ID", None)
    if not target:
        return False
    if not force and date.today().weekday() != config.WAITLIST_POST_WEEKDAY:
        return False
    url = (config.WAITLIST_URL or "").strip()
    if not url:
        print("[waitlist] WAITLIST_URL not set — skipping CTA")
        return False
    _check(requests.post(
        SEND_MESSAGE.format(token=_token_for(target)),
        data={"chat_id": target, "text": config.WAITLIST_MESSAGE.format(url=url),
              "parse_mode": "HTML"},
        timeout=30,
    ))
    print(f"[waitlist] posted CTA -> {target}")
    return True


def send(lesson: dict) -> None:
    """Broadcast the lesson to every target (owner chat + channel). PDFs are rendered
    once and reused; delivery to each target is failure-isolated so one bad target
    (e.g. a misconfigured channel) never blocks the others. After all targets are
    attempted, any failure is re-raised so the caller's run report can surface it."""
    brief_pdf, dutch_pdf = _render_pdfs(lesson)
    failed: list[str] = []
    for chat_id in _targets():
        try:
            _deliver_one(chat_id, lesson, brief_pdf, dutch_pdf)
        except Exception as exc:
            print(f"[telegram] delivery to {chat_id} failed: {exc}")
            failed.append(f"{chat_id}: {exc}")
    if failed:
        raise RuntimeError("delivery failed for " + "; ".join(failed))


def send_report(text: str) -> None:
    """Plain-text DM to the OWNER chat only (never the channel). Used by main() to
    surface stage failures from an unattended cron run; no-op when unconfigured."""
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return
    _check(requests.post(
        SEND_MESSAGE.format(token=config.TELEGRAM_BOT_TOKEN),
        data={"chat_id": config.TELEGRAM_CHAT_ID, "text": text[:MESSAGE_LIMIT]},
        timeout=30,
    ))
