"""Read deep-link feedback back from Telegram (v9 day 33).

The pipeline is a daily cron with no inbound endpoint — but it owns a bot, and
Telegram retains a bot's incoming messages for getUpdates (~24h). Buttons on the
owner DM deep-link to https://t.me/<bot>?start=<payload>; one tap sends that as a
/start message from the owner's own account. The next morning's run calls
getUpdates here, keeps recognised payloads from the OWNER chat only, and
acknowledges the batch by advancing the update offset server-side, so nothing
needs persisting locally. No webhook, no token in the browser.

Two payload kinds ride this loop:
- dr_<YYMMDD>_<marks> — Dutch trainer recall reports ("Save results" button);
  see specs/v9/day33-recall-feedback.md.
- lr_<YYMMDD>_<1-5>   — dev-lesson quality ratings (the star buttons on the
  daily lesson DM) — the feedback signal for the developer track.

One fetch serves both: acknowledging the batch drops EVERY pending update, so
all inbound payloads must be parsed from the same getUpdates call.
"""
import re
from datetime import datetime

import requests

import config

GET_UPDATES = "https://api.telegram.org/bot{token}/getUpdates"
# /start dr_<YYMMDD>_<marks>: one mark per word of that date's lesson, in the
# lesson's own word order — 1 right, 0 wrong, x not trained. Positional marks
# instead of the spec's id=0/1 pairs because real word ids blow Telegram's 64-char
# /start cap; the run already knows each lesson's word order (dutch_memory's
# lessons[].words), so positions are enough.
_REPORT = re.compile(r"^/start\s+dr_(\d{6})_([01x]+)$")
# /start lr_<YYMMDD>_<n>: a 1–5 quality rating for that date's dev lesson.
_RATING = re.compile(r"^/start\s+lr_(\d{6})_([1-5])$")
# /start rv_<YYMMDD>_<marks>: a personal cross-day REVIEW report (multi-user Phase
# 1) — marks positional over the review list published for that date (review.build).
_REVIEW = re.compile(r"^/start\s+rv_(\d{6})_([01x]+)$")


def _parse_date(yymmdd: str) -> str | None:
    try:
        return datetime.strptime(yymmdd, "%y%m%d").date().isoformat()
    except ValueError:
        return None


def fetch_inbound() -> dict[str, list]:
    """Collect pending deep-link feedback in one acknowledged batch.

    Returns {"recall": [(lesson_date_iso, marks), ...],
             "ratings": [(lesson_date_iso, rating_int), ...]}, each date-sorted.

    Owner-only: messages from chats other than TELEGRAM_CHAT_ID are skipped (but
    still acknowledged). One entry per date — the LAST one in the batch wins, so a
    re-send (a retake, a changed mind on the stars) supersedes the earlier tap.
    Every fetched update is acknowledged regardless of content, so a stray message
    can't wedge the queue.
    """
    empty: dict = {"recall": [], "ratings": [], "recall_by_user": {}, "review_by_user": {}}
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return empty
    resp = requests.get(
        GET_UPDATES.format(token=config.TELEGRAM_BOT_TOKEN),
        params={"timeout": 0, "allowed_updates": '["message"]'},
        timeout=30,
    )
    resp.raise_for_status()
    updates = resp.json().get("result", [])
    if not updates:
        return empty

    owner = str(config.TELEGRAM_CHAT_ID)
    allow = set(config.dutch_user_chat_ids())  # learners whose recall/review we accept
    recall_by_date: dict[str, str] = {}           # owner-only (backward compat)
    rating_by_date: dict[str, int] = {}           # owner-only (dev lesson rating)
    recall_users: dict[str, dict[str, str]] = {}  # chat_id -> {date: marks}
    review_users: dict[str, dict[str, str]] = {}
    for u in updates:
        msg = u.get("message") or {}
        sender = str((msg.get("chat") or {}).get("id", ""))
        text = (msg.get("text") or "").strip()
        if m := _REPORT.match(text):
            if date_iso := _parse_date(m.group(1)):
                if sender == owner:
                    recall_by_date[date_iso] = m.group(2)  # last report for a date wins
                if sender in allow:
                    recall_users.setdefault(sender, {})[date_iso] = m.group(2)
        elif m := _REVIEW.match(text):
            if (date_iso := _parse_date(m.group(1))) and sender in allow:
                review_users.setdefault(sender, {})[date_iso] = m.group(2)
        elif m := _RATING.match(text):
            if (date_iso := _parse_date(m.group(1))) and sender == owner:
                rating_by_date[date_iso] = int(m.group(2))  # last rating wins

    # Acknowledge the whole batch: a confirming getUpdates with offset just past
    # the newest update id makes Telegram drop everything we've seen, so the next
    # run starts clean. (Telegram tracks the confirmed offset server-side.)
    last_id = max(u.get("update_id", 0) for u in updates)
    requests.get(
        GET_UPDATES.format(token=config.TELEGRAM_BOT_TOKEN),
        params={"offset": last_id + 1, "timeout": 0, "limit": 1},
        timeout=30,
    )
    return {
        "recall": sorted(recall_by_date.items()),
        "ratings": sorted(rating_by_date.items()),
        "recall_by_user": {c: sorted(v.items()) for c, v in recall_users.items()},
        "review_by_user": {c: sorted(v.items()) for c, v in review_users.items()},
    }


def fetch_reports() -> list[tuple[str, str]]:
    """Pending Dutch recall reports only — see fetch_inbound. NOTE: this still
    acknowledges (drops) any pending ratings in the same batch; callers that want
    both must use fetch_inbound."""
    return fetch_inbound()["recall"]
