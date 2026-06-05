# v6 / Day 20 — KNM (Knowledge of Dutch Society)

**Goal:** add a whole inburgering exam part as a small daily habit — one bite-sized
**KNM** fact + a question each morning, cycling the official KNM themes. Grounded in a
**curated, frozen fact bank** (same discipline as the word list: facts are reviewed
data, never LLM-invented at run time), delivered in the 🇳🇱 block and tracked on the
Dutch dashboard tab.

---

## Why a curated fact bank

KNM tests specific, checkable facts about Dutch society (how the system works, rights
and duties, institutions). An LLM free-generating these will occasionally state a
wrong figure or outdated rule — unacceptable for exam prep. So, exactly as with
vocabulary: the **facts are a committed, human-reviewed asset**; the daily run only
*selects* one and (optionally) asks the LLM to phrase a question around the given
fact — never to supply the fact.

## Data: `dutch/knm.json`

```json
{
  "version": 1,
  "facts": [
    {"id": "huisarts-eerst",
     "theme": "health",
     "nl": "Bij gezondheidsklachten ga je eerst naar de huisarts; die verwijst je zo nodig door naar het ziekenhuis.",
     "en": "For health problems you first go to the GP (huisarts), who refers you to a hospital if needed.",
     "question": "Naar wie ga je eerst als je ziek bent?",
     "answer": "Naar de huisarts."}
  ]
}
```

Themes cycle the KNM domains: `work`, `health`, `housing`, `education`,
`politics` (government & constitution), `history`, `geography`, `money`, `rights`.
Seed batch: a handful per theme; grows like the word bank (reviewed, append-only).

> **Accuracy note:** KNM facts can go stale (rules/figures change). Each entry may
> carry an optional `reviewed` date; a CI test can warn when the bank hasn't been
> reviewed in N months. Exam regulations remain the user's to verify with DUO — the
> app teaches stable, general facts, not edge-case policy.

## Module: `dutch/knm.py`

```python
def load(path=KNM_FILE) -> list[dict]            # validate; [] on missing/corrupt
def pick(facts, memory, today) -> dict | None    # rotate themes; avoid recent repeats
def render(fact) -> str                          # the 🇳🇱-block KNM snippet (md)
```

`pick` rotates by theme (e.g. `today.toordinal() % len(themes)`) and avoids the last
few served ids (tracked in `dutch_memory["knm_seen"]`, a small capped list), so the
learner sees breadth, not the same fact twice in a week. No LLM call is required;
optionally `render` can ask the LLM to add a second practice question *about the given
fact text* — guarded so a bad generation just omits the extra question.

## Delivery + memory

- The KNM snippet (fact + question, NL + EN) is appended to the Dutch block in the
  email and Telegram message, under a `🇳🇱 Kennis van de samenleving` heading.
- A recall option: extend the Dutch Perplexity quiz (`followup.dutch_quiz_url`) to
  optionally include *yesterday's* KNM question, or a dedicated `knm_quiz_url`.
- `dutch_memory["knm_seen"]` records served ids (capped); the dashboard Dutch tab
  shows a small "KNM covered: X facts across Y themes" stat.

## `main.py`

Inside the existing guarded Dutch block, after the vocab lesson:

```python
fact = knm.pick(knm.load(), dmem, date.today())
if fact:
    lesson["dutch"]["knm"] = knm.render(fact)
    dmem.setdefault("knm_seen", []).append(fact["id"])   # capped in save
```

A KNM failure is swallowed like the rest of the Dutch block.

## Testing (offline)

- `knm.load`: parses the bank; `[]` on missing/corrupt.
- `knm.pick`: rotates themes across consecutive days; never returns an id in the
  recent `knm_seen` window; `None` on an empty bank.
- `knm.render`: includes the fact, question, and English gloss.
- Delivery: the KNM snippet appears in the Dutch email/Telegram block when present;
  absent cleanly when not.
- Bank integrity: ids unique; every fact has a known `theme`, `nl`, `en`, `question`.

## Acceptance criteria

- [ ] A daily KNM fact + question (NL + EN) ships in the Dutch block, theme-rotated,
      non-repeating within a short window.
- [ ] Facts come from a committed, reviewed `dutch/knm.json`; never LLM-invented.
- [ ] KNM coverage is tracked in `dutch_memory.json` and shown on the dashboard.
- [ ] Offline tests pass; ruff clean; committed pipeline state untouched.

## Out of scope

- Auto-grading KNM answers (no inbound channel — v7).
- Exhaustive/authoritative KNM coverage; the bank is a study aid, not the official
  syllabus. DUO oefenexamens remain the source of truth.
