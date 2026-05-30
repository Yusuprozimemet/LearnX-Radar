# v1 / Day 3 — Learnx audio pipeline (brief → MP3)

**Goal:** turn the Day 2 markdown brief into a single spoken-audio lesson MP3.
Ported and trimmed from LearnX-CLI (`tutor/`). Three stages from `main.py`:

```
curriculum.plan(brief_md, duration_min) -> list[TeachingUnit]   (1 LLM call)
dialogue.generate(units, title)         -> list[DialogueLine]   (N calls, concurrent)
audio_builder.build(lines, out_path)    -> writes lesson.mp3    (async; edge-tts + pydub)
```

## What we port vs. drop (from LearnX-CLI)

PORT (trimmed): `generation/curriculum.py` planner, the dialogue prompt + line
parsing from `generation/narrator.py`, `audio/tts_renderer.py`,
`audio/audio_builder.py` assembly, `audio/sanitizer.py`, the voice/silence
constants from `constants.py`.

DROP (LearnX-CLI player/video features the radar doesn't need): `timing.json`,
per-unit MP3 files + `units_dir`, chunking/summarization (our brief is small and
already structured — no `ingestion/`), all `visual/` and `player/` code,
caching. The radar produces **one MP3**, nothing else.

GENERALIZE: LearnX-CLI's prompts are Java-specific ("two Java experts",
`js_contrast`, Java code substitutions). Ours must be domain-general — the topic
is whatever the radar picked (DuckDB, WebGPU, …).

## New files

```
learnx/models.py       TeachingUnit, DialogueLine, RenderedSegment (trimmed dataclasses)
learnx/constants.py    WPM, voices, rates, silence gaps (from LearnX-CLI constants)
learnx/sanitizer.py    code→speech substitutions (general, not Java-only)
learnx/prompts/curriculum.txt
learnx/prompts/dialogue.txt
```

## Shapes

```python
@dataclass
class TeachingUnit:
    unit: int
    concept: str
    key_facts: list[str]
    analogy: str
    misconception: str
    memory_hook: str
    complexity: int       # 1|2|3
    word_budget: int

@dataclass
class DialogueLine:
    speaker: str          # "ALEX" | "MAYA"
    text: str
    unit_number: int      # 0 = intro, 1..N = unit, -1 = outro
```

## 1. `curriculum.py`

- One LLM call. Prompt reads the **whole brief** (no chunking) and the target
  duration, returns a JSON array of 3–5 units (concept, key_facts, analogy,
  misconception, memory_hook, complexity).
- Word-budget math ported from LearnX-CLI: `total_budget = duration_min*WPM -
  OVERHEAD_WORDS`; split across units by complexity. Same JSON-parse + one-retry
  guard (reuse `learnx.llm.parse_json_response`).
- `plan(brief_md, duration_min=config.LESSON_DURATION_MIN, chat_fn=chat)`.

## 2. `dialogue.py`

- For each unit, one LLM call → labeled `ALEX:` / `MAYA:` lines, parsed to
  DialogueLines (port `narrator._parse_narration`, extended for two speakers).
- **Concurrency:** unit calls run in a `ThreadPoolExecutor` (like Daily-CronJob's
  summarizer) so total latency ≈ one call, not N. Cap workers (e.g. 4).
- **Intro (unit 0) + outro (-1):** two extra short calls (or one combined),
  run in the same pool. Intro: name the skill + why it's worth 8 minutes today.
  Outro: recap the memory hooks.
- Every line passes through `sanitizer.apply` before it leaves.
- `generate(units, title, chat_fn=chat) -> list[DialogueLine]` ordered
  intro → units → outro.

## 3. `audio_builder.py`

- Port `tts_renderer.render_segment` (edge-tts; ALEX=`en-US-GuyNeural`,
  MAYA=`en-US-JennyNeural`) and the concat-with-silence assembly, **minus** the
  per-unit files and timing.json. Output: one MP3 at `out_path`.
- Async with a semaphore for concurrent TTS (port `_render_all`). Silence gaps:
  breath within a speaker, longer between turns, longest between units.
- Needs `pydub` (pip install — already in requirements) + `ffmpeg` (present).

## LLM + time budget

- curriculum (1) + dialogue (≈ N units + intro + outro, concurrent). With
  `LESSON_DURATION_MIN` and llama-3.3-70b this is a handful of calls; concurrency
  keeps wall-clock to ~1–2 min. TTS render is free (edge-tts) and concurrent.
- **Lesson length** is `config.LESSON_DURATION_MIN` (currently 8). Shorter = fewer
  words = faster/cheaper. See decision below.

## Testing

- **Offline unit tests** (`learnx/tests/`, no network/TTS):
  - `curriculum`: canned `chat_fn` JSON → assert units + word-budget math.
  - `dialogue._parse` two-speaker labels; `sanitizer.apply` substitutions;
    ordering (intro=0 … outro=-1) with a canned `chat_fn`.
  - `audio_builder` silence-gap planning (pure helper) without rendering.
- **Live integration (manual):** run `curriculum → dialogue → audio` on the saved
  `output/sample-brief.md`; assert the MP3 exists, is non-empty, and its duration
  is within ~30% of the target. Keep the MP3 for a listen.

## Decisions (signed off)

- **Two co-hosts** ALEX (male, `en-US-GuyNeural`) + MAYA (female, `JennyNeural`).
- **5-minute lesson** (`config.LESSON_DURATION_MIN = 5`).

## Acceptance criteria — DONE (2026-05-30)

- [x] `python main.py` ran end-to-end: scrape (209 items) → radar (picked "Kafka
      consumer groups") → curriculum → dialogue → audio, wrote
      `output/lesson-20260530.mp3`, halted gracefully at the delivery stubs.
      (State files were reset to clean afterward — the lesson wasn't delivered.)
- [x] Real listenable MP3 from the DuckDB brief: 5 units, 28 lines, two voices,
      4.8 min (target 5). Full audio path ~95s.
- [x] Offline unit tests pass — 27 total (parse, word-budget, sanitizer,
      intro/unit/outro ordering, silence-gap logic).
- [x] Prompts are domain-general — no Java wording (lessons: DuckDB, Kafka).

**Notes:** dialogue runs intro + N units + outro concurrently (ThreadPoolExecutor)
so wall-clock ≈ one call. Dropped LearnX-CLI's timing.json / per-unit files /
chunking / caching — radar emits one MP3. `pydub` added (ffmpeg already present).

## Out of scope

- Delivery (Day 4). Video, interactive player, Q&A, timing files (LearnX-CLI only).
