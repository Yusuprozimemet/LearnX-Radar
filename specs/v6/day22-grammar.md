# v6 / Day 22 — Grammar (weekly focus, practised in context)

**Goal:** add grammar without turning the lesson into a drill. A **rotating weekly
grammar point** (word order/V2, perfect & imperfect tense, separable verbs,
`omdat/want`, relative `die/dat`, `om…te`, comparatives…) is woven into that week's
sentences, dialogue, and reading — grammar *used*, not defined cold. A small curated
**grammar syllabus** drives the rotation; the LLM applies the point, never invents it.

---

## Why a curated syllabus + in-context practice

Two failure modes to avoid: (1) the LLM teaching a grammar rule wrong, and (2) dry
conjugation tables nobody retains. The fix mirrors the rest of v5/v6: the **rule
explanations are committed, reviewed data**; the LLM's only job is to *exemplify the
given point* inside the day's A2/B1 sentences. And because a grammar point sticks
through repetition, it is the **focus for a whole week**, not a one-off.

## Data: `dutch/grammar.json`

```json
{
  "version": 1,
  "points": [
    {"id": "perfectum",
     "cefr": "A2",
     "title_nl": "De voltooid tegenwoordige tijd (perfectum)",
     "title_en": "The present perfect",
     "rule_en": "Use 'hebben/zijn' + past participle: 'Ik heb gewerkt', 'Zij is gegaan'. Most verbs take 'hebben'; verbs of motion/change take 'zijn'.",
     "examples": [
       {"nl": "Ik heb gisteren gewerkt.", "en": "I worked yesterday."},
       {"nl": "We zijn naar de winkel gegaan.", "en": "We went to the shop."}
     ]}
  ]
}
```

Ordered roughly by difficulty and tagged `cefr`, so the rotation introduces B1
points only once the learner reaches B1 (`pacing.cefr_for`).

## Module: `dutch/grammar.py`

```python
def load(path=GRAMMAR_FILE) -> list[dict]
def point_for_week(points, memory, today, *, cefr) -> dict | None
    # deterministic weekly rotation (ISO week) over points at/below `cefr`,
    # avoiding recently-covered ids tracked in memory['grammar_seen']
def render(point) -> str            # the 🇳🇱-block grammar mini-explainer (md)
def focus_instruction(point) -> str # one line injected into lesson/reading prompts
```

`point_for_week` returns the same point all week (keyed by ISO week number) so it
recurs across ~7 lessons. `focus_instruction` is the bridge into generation: a single
sentence ("Where natural, use the present perfect, e.g. 'ik heb gewerkt'.") passed to
`dutch.lesson.build` and `dutch.reading.build`, which already take free-form prompt
context — so the week's grammar shows up *in the examples the learner reads and hears*.

## Delivery + dashboard

- A compact grammar explainer (title, rule, 2 examples) appears once in the Dutch
  block under `🇳🇱 Grammatica van de week` — the same every day that week, so it sinks
  in.
- The lesson/reading sentences that week naturally exercise the point (via
  `focus_instruction`), giving repeated in-context exposure.
- Dashboard Dutch tab: "This week's grammar: <title>" and a list of points covered.

## `main.py` / generator wiring

```python
gp = grammar.point_for_week(grammar.load(), dmem, date.today(), cefr=dmem.get("cefr","A2"))
focus = grammar.focus_instruction(gp) if gp else ""
dlesson = dutch_lesson.build(new_w + review_w, theme=theme, topic=topic, grammar_focus=focus)
# reading.build(..., grammar_focus=focus) likewise
if gp:
    lesson["dutch"]["grammar"] = grammar.render(gp)
```

`dutch.lesson.build` / `dutch.reading.build` gain an optional `grammar_focus=""`
parameter (default empty keeps day-16/21 behaviour and tests intact).

## Testing (offline)

- `grammar.load`: parses; `[]` on missing/corrupt.
- `point_for_week`: stable within an ISO week, advances across weeks, respects CEFR,
  skips recently-covered ids.
- `render` / `focus_instruction`: include the title/rule/examples and a usable
  one-line instruction.
- `lesson.build` / `reading.build`: when `grammar_focus` is set, the prompt contains
  it; when empty, prompts are unchanged (regression guard).

## Acceptance criteria

- [ ] A weekly grammar point (from a committed, reviewed syllabus) is explained in the
      Dutch block and exercised in that week's sentences/reading.
- [ ] The point is stable for the whole ISO week and rotates after; B1 points appear
      only at B1.
- [ ] Generators accept an optional grammar focus without breaking existing callers.
- [ ] Offline tests pass; ruff clean; committed pipeline state untouched.

## Out of scope

- Grammar exercises with auto-grading (v7).
- A complete reference grammar; the syllabus targets the inburgering B1 essentials.
