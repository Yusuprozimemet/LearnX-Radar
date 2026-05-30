"""Rank skill mentions by where the biggest learning gap is. Pure, no LLM.

score = demand_weight x novelty

- demand_weight: sum of per-source weights (config.SOURCE_WEIGHTS) over the
  distinct sources that mentioned the skill. Real job-market signal (HN Hiring,
  Stack Overflow) outweighs community buzz (dev.to, GitHub Trending).
- novelty: 1.0 if never taught; decays 1/(times_taught+1) so a skill the world
  wants but you've never been taught scores highest. (v2 deepens this with
  spaced-repetition timing.)

The world-wants-but-you-lack signal is exactly the gap the radar exists to find.
"""
import config

_DIFFICULTY_BY_EXPOSURE = ("beginner", "intermediate", "advanced")


def _demand_weight(sources: list[str]) -> float:
    return sum(
        config.SOURCE_WEIGHTS.get(s, config.DEFAULT_SOURCE_WEIGHT)
        for s in set(sources)
    )


def _novelty(skill: str, memory: dict) -> tuple[float, str]:
    """Return (novelty, suggested_difficulty) from prior teaching of `skill`."""
    entry = memory.get("skills", {}).get(skill)
    times_taught = entry["times_taught"] if entry else 0
    novelty = 1.0 / (times_taught + 1)
    difficulty = _DIFFICULTY_BY_EXPOSURE[min(times_taught, 2)]
    return novelty, difficulty


def _table_stakes_penalty(skill: str) -> float:
    """Sink ubiquitous, already-known skills so emerging ones can surface."""
    if skill.strip().lower() in config.TABLE_STAKES_SKILLS:
        return config.TABLE_STAKES_PENALTY
    return 1.0


def score(mentions: list[dict], memory: dict) -> list[dict]:
    """Return mentions enriched with scoring fields, ranked high to low."""
    scored: list[dict] = []
    for m in mentions:
        sources = m.get("sources", [])
        demand_weight = _demand_weight(sources)
        novelty, difficulty = _novelty(m["skill"], memory)
        penalty = _table_stakes_penalty(m["skill"])
        scored.append(
            {
                **m,
                "frequency": len(set(sources)),
                "demand_weight": demand_weight,
                "novelty": novelty,
                "table_stakes": penalty < 1.0,
                "suggested_difficulty": difficulty,
                "score": demand_weight * novelty * penalty,
            }
        )
    # Deterministic order: score desc, then frequency desc, then skill name asc.
    scored.sort(key=lambda s: (-s["score"], -s["frequency"], s["skill"]))
    return scored


def top(scored: list[dict]) -> dict | None:
    """The single highest-scoring skill to teach today, or None if empty."""
    return scored[0] if scored else None
