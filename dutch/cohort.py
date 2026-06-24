"""Aggregate the known multi-user cohort's Dutch learning (v11 day 40).

Pure: a list of per-learner dutch_memory dicts in, one anonymous summary dict out.
No IO, no network, and crucially **no chat id or token** in the output — only
counts and word ids, so the published cohort/<owner-token>.json reveals group
trends without identifying any learner. The owner-only gating is the token on the
file name (storage.save_cohort), matching review/ and progress/.

Activates once ALLOWED_CHAT_IDS is populated ([[day39-multiuser-dutch-personalization]]);
in single-user mode the cohort is just the owner (learners_total == 1).
"""
from __future__ import annotations

from datetime import date, timedelta

_RECALL_WINDOW_DAYS = 30


def _recall_window(memory: dict, cutoff: str) -> tuple[int, int]:
    """(right, wrong) from a learner's recall log within the window — same date
    field and window as dashboard.builder._recall_rate_html, so the cohort rate is
    the per-learner rate aggregated, not a different measure."""
    right = wrong = 0
    for r in memory.get("recall", []):
        if r.get("date", "") >= cutoff:
            right += len(r.get("right", []))
            wrong += len(r.get("wrong", []))
    return right, wrong


def _last_active(memory: dict) -> str:
    """The learner's most recent recall submission date (when they last practiced),
    or '' if they've never reported."""
    dates = [r.get("reported", "") or r.get("date", "") for r in memory.get("recall", [])]
    return max(dates) if dates else ""


def build_cohort(memories: list[dict], *, today: date | None = None) -> dict:
    """Anonymous aggregate over every learner's SR memory.

    - learners_total: how many learners are tracked.
    - active_7d / active_30d: learners who submitted a recall report in that window.
    - cohort_recall_30d: pooled right/wrong/pct across the group (None pct if none).
    - cefr_distribution: {level: count}.
    - hardest_words: ids the most learners are failing (then total fails), the
      group's shared trouble spots — the page joins ids to the word bank for nl/en.
    - daily_recall: pooled right/wrong per date, newest last (a small trend series).
    """
    today = today or date.today()
    cutoff_30 = (today - timedelta(days=_RECALL_WINDOW_DAYS)).isoformat()
    cutoff_7 = (today - timedelta(days=7)).isoformat()

    total_right = total_wrong = 0
    active_7d = active_30d = 0
    cefr: dict[str, int] = {}
    word_fails: dict[str, dict] = {}   # id -> {"fails": int, "learners": int}
    daily: dict[str, dict] = {}        # date -> {"right": int, "wrong": int}

    for memory in memories:
        right, wrong = _recall_window(memory, cutoff_30)
        total_right += right
        total_wrong += wrong

        last = _last_active(memory)
        if last >= cutoff_30:
            active_30d += 1
        if last >= cutoff_7:
            active_7d += 1

        level = str(memory.get("cefr", "") or "").strip()
        if level:
            cefr[level] = cefr.get(level, 0) + 1

        for wid, entry in memory.get("words", {}).items():
            fails = int(entry.get("recall_wrong", 0))
            if fails > 0:
                agg = word_fails.setdefault(wid, {"fails": 0, "learners": 0})
                agg["fails"] += fails
                agg["learners"] += 1

        for r in memory.get("recall", []):
            day = r.get("date", "")
            if not day:
                continue
            bucket = daily.setdefault(day, {"right": 0, "wrong": 0})
            bucket["right"] += len(r.get("right", []))
            bucket["wrong"] += len(r.get("wrong", []))

    pooled = total_right + total_wrong
    hardest = sorted(
        ({"id": wid, "fails": v["fails"], "learners_failing": v["learners"]}
         for wid, v in word_fails.items()),
        key=lambda w: (-w["learners_failing"], -w["fails"]),
    )[:10]
    daily_recall = [
        {"date": d, "right": daily[d]["right"], "wrong": daily[d]["wrong"]}
        for d in sorted(daily)
    ]

    return {
        "generated": today.isoformat(),
        "learners_total": len(memories),
        "active_7d": active_7d,
        "active_30d": active_30d,
        "cohort_recall_30d": {
            "right": total_right,
            "wrong": total_wrong,
            "pct": round(100 * total_right / pooled) if pooled else None,
        },
        "cefr_distribution": cefr,
        "hardest_words": hardest,
        "daily_recall": daily_recall,
    }
