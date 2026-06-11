# v10 / Day 35 — Insightful lessons (depth + discourse grounding)

**Goal:** make the English daily lesson feel *insightful and current*, not like a
generic encyclopedia entry read aloud. Two compounding problems were diagnosed
from a real lesson (`agentic coding`, 2026-06-11):

1. **Tone was stuck on beginner.** Difficulty is assigned per skill by exposure
   (`_DIFFICULTY_BY_EXPOSURE = beginner → intermediate → advanced` in
   [`gap_scorer`](../../radar/gap_scorer.py)). The radar surfaces a *new* skill most
   days, so almost every lesson landed on `beginner` — define-the-terms, analogy-
   heavy, shallow.
2. **Content was generic.** The brief was grounded on whatever ranked highest for
   the bare skill noun, which is **evergreen explainer pages** (`cloud.google.com/
   discover`, `ibm.com/think/topics`, an arxiv survey, a product page). The lesson
   faithfully turned an encyclopedia entry into audio. None of the *live discourse*
   that actually made the skill trend (named tools, techniques, debates) reached the
   listener.

This slice is a direct follow-up to [day24-brief-grounding.md](../v7/day24-brief-grounding.md):
Day 24 made the brief *grounded*; this makes it grounded in the *right, current*
material — and threads difficulty all the way to the spoken lines so "advanced"
actually sounds advanced.

---

## Locked design decisions

1. **Difficulty is a global override, not a rewrite of the spaced-repetition ramp.**
   `LESSON_DIFFICULTY_OVERRIDE` pins every lesson to one level and bypasses the
   per-skill `suggested_difficulty`. Set to `None` to restore the
   beginner→intermediate→advanced ramp. We keep the ramp logic intact; the override
   is a single, reversible knob (default `"advanced"`).
2. **Difficulty must reach the dialogue stage, not just the planner.** Before this
   slice, `difficulty` only flowed into `curriculum.plan` (unit planning). The
   *spoken lines* — written by `dialogue.generate` — never saw it and always forced
   an analogy + memory hook per unit, which kept the voice beginner-flavored
   regardless of level. Difficulty now threads into the intro/unit/outro prompts and
   **analogies become optional** (advanced → skip unless they sharpen a point).
3. **Grounding biases toward recent discourse, deterministically.** No LLM
   reranker. The Exa query is reshaped toward the live conversation and filtered by
   recency (`GROUNDING_RECENCY_DAYS`); candidates are then **stably re-ranked** so
   evergreen explainer URLs sink and discussion sources (HN/Reddit/Lobste.rs/dev.to/
   Substack/GitHub) and the day's own scraped items float. Stable sort means the
   bias only breaks ties between similarly-relevant sources — it never promotes an
   off-topic source over an on-topic one.
4. **The brief prompt demands specifics.** A new `## What's being discussed`
   section + an "INSIGHT BAR" instruction force the model to name the concrete
   tools, projects, techniques, and tensions in the grounding sources, preferring
   what is *new or contested* over textbook definitions. This is only as good as the
   sources decision 3 feeds it — the two changes are designed to compound.
5. **No section-parse breakage.** `## Do this in 5 minutes` is unchanged, so
   [`brief_writer.action_step`](../../radar/brief_writer.py) and the audio pipeline
   keep working. The new section is inserted, not substituted.

---

## Changes

### Lesson depth (difficulty → tone)

| File | Change |
|---|---|
| [config.py](../../config.py) | `LESSON_DIFFICULTY_OVERRIDE = "advanced"` (None → restore per-skill ramp) |
| [main.py](../../main.py) | difficulty = override or `suggested_difficulty`; passed into `dialogue.generate` |
| [learnx/dialogue.py](../../learnx/dialogue.py) | `generate(..., difficulty=DEFAULT_DIFFICULTY)`; injects `DIFFICULTY_CONTEXT` into intro/unit/outro prompts |
| [learnx/prompts/dialogue.txt](../../learnx/prompts/dialogue.txt), [intro.txt](../../learnx/prompts/intro.txt), [outro.txt](../../learnx/prompts/outro.txt) | new `LISTENER LEVEL:` block; analogy rule made conditional (advanced → optional) |

### Discourse grounding (sources → insight)

| File | Change |
|---|---|
| [radar/research/exa.py](../../radar/research/exa.py) | `search()` gains `start_published_date` / `category` to target fresh, discussion-shaped results |
| [radar/brief_writer.py](../../radar/brief_writer.py) | discourse-flavored Exa query + recency window; `_discourse_bias` stable re-rank sinks `/what-is`·`/topics`·`/think`·`/wiki` explainers, floats discussion hosts + day items |
| [radar/prompts/brief.txt](../../radar/prompts/brief.txt) | INSIGHT BAR + `## What's being discussed` section; `## Core ideas` told to lean on the named specifics |
| [config.py](../../config.py) | `GROUNDING_RECENCY_DAYS = 120` (None → no recency filter) |

### Dev tooling

- [scripts/preview_lesson.py](../../scripts/preview_lesson.py) — preview one lesson
  end-to-end with no scrape/deliver. `--regen "<skill>"` regenerates the **brief**
  through the grounding pipeline (pulling evidence/sources from
  `storage/last_scored.json`) so the grounding change can be A/B'd before commit.
  Kept as a dev tool, not part of the cron path.

---

## Result (A/B on `agentic coding`, 2026-06-11)

Same skill, same `advanced` tag, brief regenerated through the new grounding:

| | Before | After |
|---|---|---|
| Sources | Google Cloud "what is", ibm.com/think, arxiv survey, product page | Simon Willison substack, HN thread, "skills → loops" post, stackoverflow.blog decision-fatigue |
| Brief named | (nothing specific) | Claude Code, OpenAI Codex, Agentic Engineering, vibe coding, decision fatigue |
| Curriculum units | Agentic Coding Basics / Benefits / Future | Agentic Engineering / Vibe Coding / Decision Fatigue / Coding-Agent Prompting |

The lesson moved from a definitional overview to the actual current conversation.

> **Honest caveats.** (1) Quality now depends on what Exa surfaces that day — the
> *mechanism* reaches for live discourse, but a thin news day still yields a thinner
> brief. (2) The dialogue stage can still invent generic scenarios (a stray
> "autonomous vehicles" example appeared in the last unit); anchoring units to the
> brief's named specifics is a candidate follow-up. (3) The A/B was Exa-only
> (`items=[]`); in production the day's scraped threads also feed in and get the
> discourse boost, so production should be at least this good.

---

## Testing

- Existing offline suites unchanged and green: `learnx` (dialogue/curriculum),
  `radar/research` (exa kwargs are additive — `search(query, limit)` still valid),
  `radar` (gap scorer). `ruff` clean.
- Manual: `python scripts/preview_lesson.py --regen "agentic coding" advanced`
  produces a brief citing real, recent discourse URLs and an MP3.

## Acceptance criteria

- [x] Every lesson defaults to `advanced`; `LESSON_DIFFICULTY_OVERRIDE = None`
      restores the per-skill ramp.
- [x] `difficulty` reaches the dialogue prompts; advanced lessons drop forced
      analogies and lead with mechanics/trade-offs.
- [x] Grounding prefers recent discussion over evergreen explainers; the brief
      gains a `## What's being discussed` section that names specifics.
- [x] `## Do this in 5 minutes` preserved; `action_step` + audio pipeline unaffected.
- [x] Offline tests pass; `ruff` clean.

## Out of scope (candidate follow-ups)

- **Anchor the dialogue to named specifics** so units can't drift into invented
  generic examples (decision 2 limit).
- **Richer skill extraction (evidence)** — the upstream `evidence` string is still a
  vague umbrella (`"Agent-based software development"`); capturing the *specific*
  trending reason would sharpen the query and the whole chain. Touches the scorer.
- **Per-skill difficulty intelligence** beyond a global override (e.g. advanced
  floor but beginner for genuinely foreign topics).
