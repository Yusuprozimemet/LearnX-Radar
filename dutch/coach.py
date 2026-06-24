"""Mistake-driven coaching for the daily Dutch lesson (v10 day 36).

The lesson is otherwise chosen mechanically: theme by the calendar, new words the
first never-introduced of that theme, review words whatever's due. The recall loop
(v9 day 33) records which words the learner gets wrong, but that signal only retimes
spaced repetition — it never changes WHAT gets taught. This closes that gap: a small
LLM coach reads the accrued recall history and chooses today's focus — which
struggling words to pull forward, and a directive the lesson prompt emphasizes — so
the lesson targets the learner's own weak spots, aimed at the inburgering goal.

Two stages, mirroring radar/alias_curator: detection is deterministic and pure
(`detect_struggling`); the judgment is one injectable LLM call (`plan`). The coach
NEVER invents vocabulary — `focus_ids` are always a subset of the already-struggling
curated words; anything else the model returns is dropped (conservative, like the
curator). The asymmetry is deliberate: over-drilling discourages, so the focus is
capped tight; under-drilling just costs a little and self-heals next run.
"""
from __future__ import annotations

import logging
from collections import Counter
from collections.abc import Callable
from datetime import date

import config
from dutch.prompt_loader import load_prompt
from learnx.llm import chat, parse_json_response
from storage.paths import _DATA_DIR

log = logging.getLogger(__name__)

ChatFn = Callable[..., str]

LOG_FILE = _DATA_DIR / "dutch_coach_log.md"

_EMPTY_PLAN = {"focus_ids": [], "directive": "", "reason": ""}


def detect_struggling(
    memory: dict,
    bank: list[dict],
    *,
    min_misses: int = config.DUTCH_COACH_MIN_MISSES,
) -> list[dict]:
    """The candidate set the coach reasons over — pure, deterministic, no LLM.

    A word is struggling when `recall_wrong > recall_right` (net failing) and
    `recall_wrong >= min_misses` (one slip isn't a pattern). Words with no recall
    data are not struggling (unknown != failing), so a brand-new learner yields an
    empty set and the lesson falls back to mechanical selection. Returned with the
    curated gloss attached and ranked by miss rate, then absolute misses.
    """
    by_id = {w["id"]: w for w in bank}
    out: list[dict] = []
    for wid, entry in memory.get("words", {}).items():
        wrong = int(entry.get("recall_wrong", 0))
        right = int(entry.get("recall_right", 0))
        if wrong < min_misses or wrong <= right:
            continue
        word = by_id.get(wid)
        if word is None:
            continue  # id no longer in the frozen bank
        out.append({
            "id": wid,
            "nl": word.get("nl", ""),
            "en": word.get("en", ""),
            "wrong": wrong,
            "right": right,
        })
    out.sort(key=lambda w: (w["wrong"] / (w["wrong"] + w["right"]), w["wrong"]), reverse=True)
    return out


def confusable_pairs(
    memory: dict,
    bank: list[dict],
    *,
    min_misses: int = config.DUTCH_COACH_STUCK_MISSES,
    max_pairs: int = config.DUTCH_COACH_MAX_CONTRAST,
) -> list[dict]:
    """The coach's second tool — pure, deterministic, no LLM.

    A word is STUCK when it's been recalled wrong ``>= min_misses`` times with ZERO
    successful recalls: re-exposure isn't working, so it's almost certainly confused
    with a neighbour rather than simply unlearned (``email`` failed x3, never right).
    For each stuck word, the partner is the word the learner most often gets wrong IN
    THE SAME report — their own confusion signal — so the pair is grounded in real
    data, and both words come from the frozen bank. Returns at most ``max_pairs``
    ``{id, nl, en, with_id, with_nl, with_en}`` dicts, most-missed first; a stuck word
    that never co-failed with anything yields no pair (nothing to contrast it against).
    """
    by_id = {w["id"]: w for w in bank}
    words = memory.get("words", {})
    recall = memory.get("recall", [])
    stuck = [
        wid
        for wid, e in words.items()
        if int(e.get("recall_wrong", 0)) >= min_misses
        and int(e.get("recall_right", 0)) == 0
        and wid in by_id
    ]
    stuck.sort(key=lambda wid: -int(words[wid].get("recall_wrong", 0)))

    pairs: list[dict] = []
    used: set[frozenset[str]] = set()
    for wid in stuck:
        co: Counter[str] = Counter()
        for r in recall:
            wrong = r.get("wrong", [])
            if wid in wrong:
                co.update(o for o in wrong if o != wid and o in by_id)
        if not co:
            continue
        partner = co.most_common(1)[0][0]
        key = frozenset((wid, partner))
        if key in used:
            continue
        used.add(key)
        a, b = by_id[wid], by_id[partner]
        pairs.append({
            "id": wid, "nl": a.get("nl", ""), "en": a.get("en", ""),
            "with_id": partner, "with_nl": b.get("nl", ""), "with_en": b.get("en", ""),
        })
        if len(pairs) >= max_pairs:
            break
    return pairs


def render_contrast(pairs: list[dict]) -> str:
    """A 'mind the difference' markdown section for the confusable pairs — gloss-only,
    so nothing is invented (the words and meanings come straight from the frozen bank).
    Empty string when there are no pairs, so the section simply doesn't render."""
    if not pairs:
        return ""
    out = [
        "**Let op het verschil (mind the difference)**",
        "_Je verwart deze woorden — gebruik elk in een eigen zin._ "
        "_(You keep mixing these up — use each in its own sentence.)_",
    ]
    out += [
        f"- **{p['nl']}** _({p['en']})_ ↔ **{p['with_nl']}** _({p['with_en']})_"
        for p in pairs
    ]
    return "\n".join(out)


def _format(struggling: list[dict]) -> str:
    return "\n".join(
        f"- {w['id']} — {w['nl']} — {w.get('en', '')} "
        f"(missed {w['wrong']}x, recalled {w['right']}x)"
        for w in struggling
    )


def plan(
    struggling: list[dict],
    *,
    max_focus: int = config.DUTCH_COACH_MAX_FOCUS,
    chat_fn: ChatFn = chat,
) -> dict:
    """Choose today's focus from the struggling words (one LLM call, injectable).

    Returns ``{"focus_ids": [...], "directive": str, "reason": str}``. ``focus_ids``
    is always a SUBSET of the struggling ids, capped at ``max_focus`` (others
    dropped — no hallucinated words). When ``struggling`` is empty the coach is
    skipped entirely: no LLM call, an empty plan returned. Any parse/LLM failure
    also degrades to the empty plan so the lesson still ships mechanically.
    """
    if not struggling:
        return dict(_EMPTY_PLAN)
    valid = {w["id"] for w in struggling}
    prompt = load_prompt("coach.txt").format(max_focus=max_focus, words=_format(struggling))
    try:
        raw = chat_fn([{"role": "user", "content": prompt}], temperature=0.0, max_tokens=400)
        data = parse_json_response(raw)
    except Exception as exc:  # degrade: no focus today, mechanical selection stands
        log.warning("Dutch coach plan failed (%s); no focus today", exc)
        return dict(_EMPTY_PLAN)
    if not isinstance(data, dict):
        return dict(_EMPTY_PLAN)
    focus = [i for i in data.get("focus_ids", []) if isinstance(i, str) and i in valid][:max_focus]
    return {
        "focus_ids": focus,
        # No focus -> no directive (an empty directive leaves the lesson prompt
        # byte-identical to the mechanical one).
        "directive": str(data.get("directive", "")).strip() if focus else "",
        "reason": str(data.get("reason", "")).strip(),
    }


def append_log(
    plan_result: dict,
    struggling: list[dict],
    *,
    when: date | None = None,
    path=LOG_FILE,
) -> None:
    """Append one plan to the audit log — the same human-on-the-loop trail the alias
    curator keeps. The learner reviews it to see when the coach helps vs. nags."""
    day = (when or date.today()).isoformat()
    focus = plan_result.get("focus_ids", [])
    cand = ", ".join(f"{w['id']}({w['wrong']}/{w['right']})" for w in struggling)
    lines = [
        f"\n## {day} — focus: {', '.join(focus) if focus else '(none)'}",
        f"- directive: {plan_result.get('directive', '') or '(none)'}",
        f"- reason: {plan_result.get('reason', '') or '(none)'}",
        f"- struggling ({len(struggling)}): {cand}",
    ]
    header = "# Mistake-driven Dutch coach — plan log\n"
    prior = path.read_text(encoding="utf-8") if path.exists() else header
    path.write_text(prior + "\n".join(lines) + "\n", encoding="utf-8")
