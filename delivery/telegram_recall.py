"""Read trainer recall reports back from Telegram (v9 day 33).

The pipeline is a daily cron with no inbound endpoint — but it owns a bot, and
Telegram retains a bot's incoming messages for getUpdates (~24h). The trainer
page's "Save results" button opens https://t.me/<bot>?start=dr_<YYMMDD>_<marks>;
one tap sends that as a /start message from the learner's own account. The next
morning's run calls getUpdates here, keeps `/start dr_…` messages from the OWNER
chat only (this is the personal learning loop — multi-user waits for the
personalization track), and acknowledges the batch by advancing the update offset
server-side, so nothing needs persisting locally. No webhook, no token in the
browser. See specs/v9/day33-recall-feedback.md.
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


def fetch_reports() -> list[tuple[str, str]]:
    """Collect pending recall reports: [(lesson_date_iso, marks), ...], date-sorted.

    Owner-only: messages from chats other than TELEGRAM_CHAT_ID are skipped (but
    still acknowledged). One report per date — the LAST one in the batch wins, so a
    re-send after a retake supersedes the earlier tap. Every fetched update is
    acknowledged regardless of content, so a stray message can't wedge the queue.
    """
    if not (config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID):
        return []
    resp = requests.get(
        GET_UPDATES.format(token=config.TELEGRAM_BOT_TOKEN),
        params={"timeout": 0, "allowed_updates": '["message"]'},
        timeout=30,
    )
    resp.raise_for_status()
    updates = resp.json().get("result", [])
    if not updates:
        return []

    by_date: dict[str, str] = {}
    for u in updates:
        msg = u.get("message") or {}
        if str((msg.get("chat") or {}).get("id", "")) != str(config.TELEGRAM_CHAT_ID):
            continue
        m = _REPORT.match((msg.get("text") or "").strip())
        if not m:
            continue
        yymmdd, marks = m.groups()
        try:
            date_iso = datetime.strptime(yymmdd, "%y%m%d").date().isoformat()
        except ValueError:
            continue
        by_date[date_iso] = marks  # last report for a date wins

    # Acknowledge the whole batch: a confirming getUpdates with offset just past
    # the newest update id makes Telegram drop everything we've seen, so the next
    # run starts clean. (Telegram tracks the confirmed offset server-side.)
    last_id = max(u.get("update_id", 0) for u in updates)
    requests.get(
        GET_UPDATES.format(token=config.TELEGRAM_BOT_TOKEN),
        params={"offset": last_id + 1, "timeout": 0, "limit": 1},
        timeout=30,
    )
    return sorted(by_date.items())
