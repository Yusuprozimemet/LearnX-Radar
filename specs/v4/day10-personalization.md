# v4 / Day 10 — Personalization (scoring that knows *me*)

**Goal:** make the daily topic about *my* trajectory, not the global developer
world. Skills I already know should sink; skills on my stated learning path should
rise. Today the only "what does the user know" signal is the global
`TABLE_STAKES_SKILLS` set — identical for everyone. This generalizes it to a
per-user profile, with no new file and no new dependency.

## Why in `config.py`

The profile is just more tunable knobs, exactly like `SOURCE_WEIGHTS`,
`TABLE_STAKES_SKILLS`, and `SR_BASE_INTERVAL_DAYS` already are. Putting it there
keeps the one-edit-place discipline and avoids a YAML/JSON loader + dependency.
(A `profile.yaml` could be added later if the profile outgrows code; not now.)

## Config (`config.py`)

A new "Personalization" section:

```python
# --- Personalization: the profile the radar scores against ---
# Skills you already have — sunk like table-stakes so the radar stops offering
# them. Matched exactly, normalized (lowercased, stripped), same as TABLE_STAKES.
KNOWN_SKILLS = {"python", "fastapi", "docker"}          # example; user edits

# Topics on your learning path — skills matching any of these (substring, both
# directions, normalized) get boosted so your goals surface sooner.
LEARNING_GOALS = ["distributed systems", "rust", "llm agents"]  # example

KNOWN_PENALTY = 0.1   # multiplier for a KNOWN_SKILLS hit (0 = drop; 1 = no effect)
GOAL_BOOST    = 1.5   # multiplier when a skill matches a LEARNING_GOALS entry
```

Defaults ship as illustrative examples with a comment telling the user to edit
them. Empty `KNOWN_SKILLS` / `LEARNING_GOALS` make the profile a no-op, so the
pipeline behaves exactly as v3 until the user fills it in.

## Scoring (`radar/gap_scorer.py`)

`score()` gains an optional `profile` so callers and tests stay back-compatible:

```python
def score(mentions, memory, profile=None): ...
```

Two new pure helpers, mirroring the existing `_table_stakes_penalty`:

- `_known_penalty(skill, known)` → `config.KNOWN_PENALTY` if the normalized skill
  is in `known`, else `1.0`.
- `_goal_boost(skill, goals)` → `config.GOAL_BOOST` if the normalized skill
  matches any goal (substring either direction), else `1.0`.

The score line extends to:

```
score = demand_weight * novelty * table_stakes_penalty * known_penalty * goal_boost
```

When `profile` is `None`, both new factors are `1.0` and the result is identical to
v3. Add `"known"` (bool) and `"goal_match"` (bool) to each scored dict so the
dashboard/brief can later show *why* a topic surfaced. Deterministic sort unchanged.

`profile` is a small dict assembled in `main()` from the config constants:
`{"known": config.KNOWN_SKILLS, "goals": config.LEARNING_GOALS}`.

## Wiring (`main.py`)

One line: build `profile` from config and pass it to `gap_scorer.score(mentions,
memory, profile)`. Nothing else in the pipeline changes.

## Testing (offline)

- `score()` with `profile=None` returns byte-for-byte the v3 result (regression).
- A `KNOWN_SKILLS` hit is sunk below an equally-demanded unknown skill.
- A `LEARNING_GOALS` match outranks an equally-demanded non-goal skill.
- Goal match is case-insensitive and works both substring directions
  ("rust" ↔ "rust async", "llm agents" ↔ "llm").
- A skill that is both known and table-stakes is still just sunk (penalties
  compose without error, score stays ≥ 0).

## Acceptance criteria

- [ ] `config.py` has the Personalization section; empty profile = v3 behavior.
- [ ] `gap_scorer.score()` takes optional `profile`; known sink, goals rise.
- [ ] Scored dicts carry `known` / `goal_match` flags.
- [ ] `main()` passes the profile through.
- [ ] Offline tests pass; ruff clean.

## Out of scope

- A separate `profile.yaml`/loader (revisit only if the profile outgrows config).
- LLM-based goal/skill semantic matching (keep `gap_scorer` pure and LLM-free;
  substring matching is enough and deterministic).
- Showing the `known`/`goal_match` flags on the dashboard (data is emitted now;
  rendering is a later dashboard tweak).
