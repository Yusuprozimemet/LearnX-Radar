"""Rank skill mentions by where the biggest learning gap is. Pure, no LLM.

score = demand_weight x novelty

- demand_weight: sum of per-source weights (config.SOURCE_WEIGHTS) over the
  distinct sources that mentioned the skill. Real job-market signal (HN Hiring,
  Stack Overflow) outweighs community buzz (dev.to, GitHub Trending).
- novelty (v2, spaced repetition): 1.0 if never taught. Once taught, a skill is
  suppressed (~0) and recovers toward 1.0 only after a spacing interval that
  widens with each repetition — so the radar revisits topics on a schedule
  instead of either re-teaching daily or never again.

The world-wants-but-you-lack signal is exactly the gap the radar exists to find.
"""
from datetime import date

import config

_DIFFICULTY_BY_EXPOSURE = ("beginner", "intermediate", "advanced")


def _demand_weight(sources: list[str]) -> float:
    return sum(
        config.SOURCE_WEIGHTS.get(s, config.DEFAULT_SOURCE_WEIGHT)
        for s in set(sources)
    )


def _days_since(iso_date: str | None) -> int | None:
    if not iso_date:
        return None
    try:
        return (date.today() - date.fromisoformat(iso_date)).days
    except ValueError:
        return None


def _novelty(skill: str, memory: dict, today_days=_days_since) -> tuple[float, str]:
    """Return (novelty, suggested_difficulty) for `skill` given prior teaching.

    Spaced repetition: novelty = clamp(days_since_last / interval, 0, 1), where
    the interval widens with each repetition. Unseen skills are fully novel.
    """
    entry = memory.get("skills", {}).get(skill)
    times_taught = entry["times_taught"] if entry else 0
    if times_taught <= 0:
        return 1.0, _DIFFICULTY_BY_EXPOSURE[0]

    difficulty = _DIFFICULTY_BY_EXPOSURE[min(times_taught, 2)]
    days = today_days(entry.get("last_taught"))
    if days is None:  # taught but no/invalid date — treat as due again
        return 1.0, difficulty

    interval = config.SR_BASE_INTERVAL_DAYS * (config.SR_SPACING_FACTOR ** (times_taught - 1))
    novelty = max(0.0, min(1.0, days / interval))
    return novelty, difficulty


def _table_stakes_penalty(skill: str) -> float:
    """Sink ubiquitous, already-known skills so emerging ones can surface."""
    if skill.strip().lower() in config.TABLE_STAKES_SKILLS:
        return config.TABLE_STAKES_PENALTY
    return 1.0


def _known_penalty(skill: str, known: set[str]) -> float:
    """Sink skills the user already has (the personal analogue of table-stakes)."""
    if skill.strip().lower() in {k.strip().lower() for k in known}:
        return config.KNOWN_PENALTY
    return 1.0


def _goal_match(skill: str, goals: list[str]) -> bool:
    """True if the skill relates to any learning goal (substring, either way)."""
    s = skill.strip().lower()
    return any(
        (g := goal.strip().lower()) and (g in s or s in g)
        for goal in goals
    )


def score(mentions: list[dict], memory: dict, profile: dict | None = None) -> list[dict]:
    """Return mentions enriched with scoring fields, ranked high to low.

    `profile` (v4) personalizes the ranking: {"known": set, "goals": list}. Known
    skills sink (you already have them); goal-relevant skills rise. When None, both
    factors are 1.0 and the result is identical to the global v3 scoring.
    """
    known = profile.get("known", set()) if profile else set()
    goals = profile.get("goals", []) if profile else []
    scored: list[dict] = []
    for m in mentions:
        sources = m.get("sources", [])
        demand_weight = _demand_weight(sources)
        novelty, difficulty = _novelty(m["skill"], memory)
        penalty = _table_stakes_penalty(m["skill"])
        known_pen = _known_penalty(m["skill"], known)
        goal_hit = _goal_match(m["skill"], goals)
        boost = config.GOAL_BOOST if goal_hit else 1.0
        scored.append(
            {
                **m,
                "frequency": len(set(sources)),
                "demand_weight": demand_weight,
                "novelty": novelty,
                "table_stakes": penalty < 1.0,
                "known": known_pen < 1.0,
                "goal_match": goal_hit,
                "suggested_difficulty": difficulty,
                "score": demand_weight * novelty * penalty * known_pen * boost,
            }
        )
    # Deterministic order: score desc, then frequency desc, then skill name asc.
    scored.sort(key=lambda s: (-s["score"], -s["frequency"], s["skill"]))
    return scored


def top(scored: list[dict]) -> dict | None:
    """The single highest-scoring skill to teach today, or None if empty."""
    return scored[0] if scored else None
