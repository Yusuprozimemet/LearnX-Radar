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
from learnx.constants import DIALOGUE_MAX_WORKERS
from learnx.llm import chat
from learnx.models import DialogueLine, TeachingUnit
from learnx.prompt_loader import load_prompt

log = logging.getLogger(__name__)

_LINE_RE = re.compile(r"^(ALEX|MAYA)\s*[:\-]\s*(.+)", re.IGNORECASE)


def generate(
    units: list[TeachingUnit], title: str, hook: str = "", action: str = "", chat_fn=chat
) -> list[DialogueLine]:
    """Return ordered dialogue lines: intro (0) -> units (1..N) -> outro (-1).

    `action` (v4) is the brief's "Do this in 5 minutes" step; when given, the outro
    closes by voicing it as a quick call to action.
    """
    if not units:
        return []

    hooks = " ".join(u.memory_hook for u in units if u.memory_hook)
    # Each task is (unit_number, prompt). Run them all concurrently.
    tasks: list[tuple[int, str]] = [(0, _intro_prompt(title, hook or units[0].concept))]
    tasks += [(u.unit, _unit_prompt(u, title)) for u in units]
    tasks.append((-1, _outro_prompt(title, hooks, action)))

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


def _unit_prompt(u: TeachingUnit, title: str) -> str:
    return load_prompt("dialogue.txt").format(
        title=title,
        concept=u.concept,
        word_budget=u.word_budget,
        key_facts="; ".join(u.key_facts) or "(none)",
        analogy=u.analogy or "(none)",
        misconception=u.misconception or "(none)",
        memory_hook=u.memory_hook or "(none)",
    )


def _intro_prompt(title: str, hook: str) -> str:
    return load_prompt("intro.txt").format(title=title, hook=hook)


def _outro_prompt(title: str, hooks: str, action: str = "") -> str:
    return load_prompt("outro.txt").format(
        title=title, hooks=hooks or "(none)", action=action or "(none)"
    )
