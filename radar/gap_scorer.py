"""Rank skill mentions by where the biggest learning gap is. Pure, no LLM.

score = demand_weight x novelty x table_stakes x known x goal x momentum

- demand_weight: sum of per-source weights (config.SOURCE_WEIGHTS) over the
  distinct sources that mentioned the skill. Real job-market signal (HN Hiring,
  Stack Overflow) outweighs community buzz (dev.to, GitHub Trending).
- novelty (v2, spaced repetition): 1.0 if never taught. Once taught, a skill is
  suppressed (~0) and recovers toward 1.0 only after a spacing interval that
  widens with each repetition — so the radar revisits topics on a schedule
  instead of either re-teaching daily or never again.
- momentum (v7 Day26): rewards skills RISING across days (vs one-day spikes), from
  trending_history matched by canonical name. Orthogonal to novelty.

The world-wants-but-you-lack signal is exactly the gap the radar exists to find.
"""
from datetime import date

import config

# Reuse the SAME canonicalization extraction used to merge variants, so cross-day
# matching links the same skill across days (e.g. k8s <-> Kubernetes).
from radar.skill_extractor import _canonical

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


def _momentum(skill: str, demand_weight: float, history: dict | None) -> float:
    """Multiplier rewarding a skill that's RISEN across recent days, not just today.

    Looks back over MOMENTUM_WINDOW_DAYS of `history` (one ranking per day), matched
    by canonical name. Seen only today -> SPIKE_DAMP. Seen across prior days -> boost
    scaled by recurrence, full only if today's demand also accelerates vs the prior
    average (flat/declining halves the boost). Returns 1.0 when disabled / no history.
    """
    if not config.MOMENTUM_ENABLED or not history:
        return 1.0
    canon = _canonical(skill)
    today = date.today().isoformat()
    days = [d for d in sorted(history, reverse=True) if d != today][
        : config.MOMENTUM_WINDOW_DAYS
    ]
    if not days:
        return 1.0  # no prior history to judge against

    prior_demand: list[float] = []
    for d in days:
        for row in history[d].get("scored", []):
            if _canonical(str(row.get("skill", ""))) == canon:
                dw = row.get("demand_weight")
                if isinstance(dw, (int, float)):
                    prior_demand.append(dw)
                break

    if not prior_demand:
        return config.MOMENTUM_SPIKE_DAMP  # appears only today -> one-day spike

    recurrence = len(prior_demand) / len(days)  # of days we have, how often present
    boost = 1.0 + (config.MOMENTUM_MAX_BOOST - 1.0) * recurrence
    prior_avg = sum(prior_demand) / len(prior_demand)
    if demand_weight <= prior_avg:  # sustained but not accelerating -> half the boost
        boost = 1.0 + (boost - 1.0) * 0.5
    return boost


def score(
    mentions: list[dict],
    memory: dict,
    profile: dict | None = None,
    history: dict | None = None,
) -> list[dict]:
    """Return mentions enriched with scoring fields, ranked high to low.

    `profile` (v4) personalizes the ranking: {"known": set, "goals": list}. Known
    skills sink (you already have them); goal-relevant skills rise. When None, both
    factors are 1.0 and the result is identical to the global v3 scoring.

    `history` (v7 Day26) is trending_history (prior-day rankings) for the momentum
    multiplier; when None or MOMENTUM_ENABLED is False, momentum is 1.0 (no effect).
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
        momentum = _momentum(m["skill"], demand_weight, history)
        scored.append(
            {
                **m,
                "frequency": len(set(sources)),
                "demand_weight": demand_weight,
                "novelty": novelty,
                "table_stakes": penalty < 1.0,
                "known": known_pen < 1.0,
                "goal_match": goal_hit,
                "momentum": momentum,
                "canonical": _canonical(m["skill"]),
                "suggested_difficulty": difficulty,
                "score": demand_weight * novelty * penalty * known_pen * boost * momentum,
            }
        )
    # Deterministic order: score desc, then frequency desc, then skill name asc.
    scored.sort(key=lambda s: (-s["score"], -s["frequency"], s["skill"]))
    return scored


def top(scored: list[dict]) -> dict | None:
    """The single highest-scoring skill to teach today, or None if empty."""
    return scored[0] if scored else None
