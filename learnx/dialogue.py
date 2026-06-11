"""Two-co-host dialogue generator — ported from LearnX-CLI narrator/dialogue.

Each teaching unit becomes a stretch of ALEX/MAYA dialogue. Unit calls run
concurrently (like Daily-CronJob's summarizer) so wall-clock ≈ one call. An
intro (unit 0) and outro (unit -1) bracket the lesson. Every line is sanitized
for TTS before it leaves.
"""
import logging
import re
from concurrent.futures import ThreadPoolExecutor

from learnx import sanitizer
from learnx.constants import DEFAULT_DIFFICULTY, DIALOGUE_MAX_WORKERS, DIFFICULTY_CONTEXT
from learnx.llm import chat
from learnx.models import DialogueLine, TeachingUnit
from learnx.prompt_loader import load_prompt

log = logging.getLogger(__name__)

_LINE_RE = re.compile(r"^(ALEX|MAYA)\s*[:\-]\s*(.+)", re.IGNORECASE)


def generate(
    units: list[TeachingUnit],
    title: str,
    hook: str = "",
    action: str = "",
    difficulty: str = DEFAULT_DIFFICULTY,
    chat_fn=chat,
) -> list[DialogueLine]:
    """Return ordered dialogue lines: intro (0) -> units (1..N) -> outro (-1).

    `action` (v4) is the brief's "Do this in 5 minutes" step; when given, the outro
    closes by voicing it as a quick call to action. `difficulty` pitches the spoken
    lines to the listener's level (advanced -> skip definitions/analogies, lead with
    mechanics and gotchas); it mirrors the level used to plan the curriculum.
    """
    if not units:
        return []

    context = DIFFICULTY_CONTEXT.get(difficulty, DIFFICULTY_CONTEXT[DEFAULT_DIFFICULTY])
    hooks = " ".join(u.memory_hook for u in units if u.memory_hook)
    # Each task is (unit_number, prompt). Run them all concurrently.
    tasks: list[tuple[int, str]] = [(0, _intro_prompt(title, hook or units[0].concept, context))]
    tasks += [(u.unit, _unit_prompt(u, title, context)) for u in units]
    tasks.append((-1, _outro_prompt(title, hooks, action, context)))

    def run(task: tuple[int, str]) -> tuple[int, str]:
        unit_no, prompt = task
        return unit_no, chat_fn([{"role": "user", "content": prompt}], max_tokens=1200)

    workers = min(DIALOGUE_MAX_WORKERS, len(tasks))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(run, tasks))

    # Reassemble in lesson order: 0, 1..N, then -1.
    by_unit = {unit_no: raw for unit_no, raw in results}
    ordered = [0] + [u.unit for u in units] + [-1]
    lines: list[DialogueLine] = []
    for unit_no in ordered:
        lines.extend(_parse(by_unit.get(unit_no, ""), unit_no))
    log.info("Generated %d dialogue lines across %d sections", len(lines), len(ordered))
    return lines


def _parse(raw: str, unit_number: int) -> list[DialogueLine]:
    lines: list[DialogueLine] = []
    for raw_line in raw.split("\n"):
        match = _LINE_RE.match(raw_line.strip())
        if not match:
            continue
        speaker = match.group(1).upper()
        text = sanitizer.apply(match.group(2))
        if text:
            lines.append(DialogueLine(speaker=speaker, text=text, unit_number=unit_number))
    return lines


_DEFAULT_CONTEXT = DIFFICULTY_CONTEXT[DEFAULT_DIFFICULTY]


def _unit_prompt(u: TeachingUnit, title: str, difficulty_context: str = _DEFAULT_CONTEXT) -> str:
    return load_prompt("dialogue.txt").format(
        difficulty_context=difficulty_context,
        title=title,
        concept=u.concept,
        word_budget=u.word_budget,
        key_facts="; ".join(u.key_facts) or "(none)",
        analogy=u.analogy or "(none)",
        misconception=u.misconception or "(none)",
        memory_hook=u.memory_hook or "(none)",
    )


def _intro_prompt(title: str, hook: str, difficulty_context: str = _DEFAULT_CONTEXT) -> str:
    return load_prompt("intro.txt").format(
        difficulty_context=difficulty_context, title=title, hook=hook
    )


def _outro_prompt(
    title: str, hooks: str, action: str = "", difficulty_context: str = _DEFAULT_CONTEXT
) -> str:
    return load_prompt("outro.txt").format(
        difficulty_context=difficulty_context,
        title=title,
        hooks=hooks or "(none)",
        action=action or "(none)",
    )
