# v4 / Day 11 — Actionable briefs + recall quiz link

**Goal:** make each lesson *do* something and let me *test* myself. Two changes to
the lesson payload, shipped together because both change what the learner receives:
(1) the brief gains a concrete "Do this in 5 minutes" action; (2) a second,
additive Perplexity link runs a short recall quiz. Neither needs new infrastructure.

---

## Part A — Actionable briefs (`radar/prompts/brief.txt`)

Today's briefs are all prose and end with "Where it fits" — the learner finishes
knowing *about* a topic with nothing to do. Add a final section to the brief
prompt:

> **## Do this in 5 minutes**
> One concrete, tiny exercise the reader can do right now: a command to run, a
> short code snippet to type and execute, or one specific repo/doc to skim. Be
> specific and runnable — no "go explore the ecosystem" filler.

Constraints in the prompt: keep it to one action, prefer something doable in a
terminal or a scratch file, include a code/command snippet when the skill is
code-shaped. `brief_writer.write()` is otherwise unchanged (still one LLM call;
bump `max_tokens` only if briefs truncate — verify against a live run).

### Extracting the action

The brief stays a single markdown string (`write()` does not change its return
type). A separate, deterministic helper pulls the action out of it:

- `brief_writer.action_step(brief_md) -> str` — a regex captures the body under the
  `## Do this in 5 minutes` heading up to the next heading (or end of document),
  returning the stripped text or `""` when the section is absent.

`main()` calls `action_step(brief_md)` and threads the result into the audio path
(see below); it is not stored on the `lesson` payload, since the only consumer is
the outro. (An empty action simply yields no call-to-action line.)

### Carry it into the audio

The curriculum/dialogue path turns the brief into the spoken lesson. The
"Do this in 5 minutes" action lands in the **outro** so the lesson ends on a call
to action ("before you go, try this: …").

This is a small **structural** change, not a pure prompt tweak (the outro only ever
saw the units' memory-hooks, never the brief tail):

- `dialogue.generate(units, title, hook="", action="", chat_fn=chat)` gains an
  `action` parameter (default `""` keeps callers/tests back-compatible).
- The internal `dialogue._outro_prompt(title, hooks, action="")` passes `action`
  into `outro.txt`, which gains an `{action}` placeholder. The outro is instructed
  to voice it as a "before you go, try this" line when present, and to omit it when
  `action` is `(none)`.
- `main()` is the caller that wires it: `action = brief_writer.action_step(brief_md)`
  then `dialogue.generate(..., action=action)`. `curriculum.py` is **not** touched.

### Testing (offline)

- `brief_writer.write` (mocked `chat_fn`): prompt text now contains the
  "Do this in 5 minutes" instruction.
- `brief_writer.action_step`: extracts the section body from a brief that has it;
  returns `""` for a brief missing the section and for empty input.
- `dialogue._outro_prompt`: includes the action text when given; collapses to
  `(none)` when omitted.
- Existing brief/dialogue tests still pass (the section and `action` param are
  additive).

---

## Part B — Recall quiz link (`delivery/followup.py` + senders)

A **second** Perplexity deep link. The existing `perplexity_url()` (open-ended
follow-ups on *today's* brief) is **unchanged**.

### `delivery/followup.py`

Add, alongside `perplexity_url()`:

```python
def quiz_url(skill: str, brief_file: str) -> str:
    """Deep link to a Perplexity thread that quizzes the user on `skill`,
    grounded in the committed brief."""
```

Same URL shape (`.../search/new?q=<encoded>`) and same `BRIEFS_RAW_BASE + "/" +
brief_file`. The seeded query is the **one tunable line** that sets the quiz format
(default: active recall, not multiple choice):

> "Quiz me on this lesson to check what I retained. Read this brief: {brief_url}.
> Ask me 2–3 questions ONE AT A TIME — mix a recall question ('in your own
> words…') and an applied/scenario question. Wait for my answer before the next.
> After each answer, grade it and correct me using the brief. Start now."

Switching to multiple-choice later = edit this string only.

### Which brief does the quiz target?

Genuine recall = test a *prior* lesson, not the one just heard. So the quiz link
points at the **most recent previous lesson's brief**, taken from
`skill_memory.json` (the last `lessons[]` entry before today, via its `brief`
filename). `main()` already has `memory`; pass the previous lesson's
`(skill, brief_file)` into the `lesson` dict as e.g. `quiz_skill` / `quiz_brief`.
On day one (no prior lesson) these are absent and the quiz button no-ops — same
pattern as the follow-up button when no brief exists.

> Simpler alternative if preferred: quiz *today's* brief instead (reuse
> `skill`/`brief_file`). One-line change; loses the spaced-retrieval delay.

### Senders

- `telegram_sender._reply_markup`: the inline keyboard becomes two rows —
  `[🔎 Ask follow-ups on Perplexity]` (today, unchanged) and `[🧠 Quiz me on this]`
  (previous lesson). The quiz row is added only when `quiz_brief` is present.
- `email_sender`: add a second `<a>` button next to the existing one, same
  conditional.

### Testing (offline)

- `quiz_url()` returns a `perplexity.ai/search/new` URL whose decoded query
  contains the brief raw URL and "one at a time".
- `perplexity_url()` output is **unchanged** (regression guard so follow-ups stay
  intact).
- `telegram_sender._reply_markup`: two buttons when `quiz_brief` set; one button
  (follow-ups only) when not; empty when no brief at all.

## Acceptance criteria

- [ ] Briefs end with a runnable "Do this in 5 minutes" action; the outro voices it.
- [ ] A second "Quiz me" Perplexity button ships in Telegram + email, targeting the
      previous lesson's brief, no-op on day one.
- [ ] The existing "Ask follow-ups" link is byte-for-byte unchanged.
- [ ] Offline tests pass; ruff clean.

## Out of scope

- Auto-grading / persisting quiz results (needs an inbound channel — the future
  daily `getUpdates` poll, its own later spec). This quiz is self-directed only.
- Multiple-choice/matching formats (one-line query swap if ever wanted).
