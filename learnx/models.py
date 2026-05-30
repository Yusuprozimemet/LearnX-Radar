"""Dataclasses for the audio pipeline. Trimmed from LearnX-CLI (tutor/models.py).

Only what the radar needs: a teaching unit, a spoken line, and a rendered
segment. No video/visual/QA types.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TeachingUnit:
    unit: int
    concept: str
    word_budget: int
    complexity: int = 2  # 1 | 2 | 3
    key_facts: list[str] = field(default_factory=list)
    analogy: str = ""
    misconception: str = ""
    memory_hook: str = ""


@dataclass
class DialogueLine:
    speaker: str       # "ALEX" | "MAYA"
    text: str
    unit_number: int   # 0 = intro, 1..N = unit, -1 = outro


@dataclass
class RenderedSegment:
    line: DialogueLine
    audio_path: str
    duration_ms: int
