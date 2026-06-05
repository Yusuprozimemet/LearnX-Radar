"""Render the Dutch lesson to one MP3 using edge-tts Dutch voices.

Reuses learnx.audio_builder by injecting the nl-NL voice map (no English-specific
processing): the new words are read aloud (with their example sentence when one was
generated), then the dialogue. Speakers A/B map to the two Dutch co-host voices via
the ALEX/MAYA keys the builder already understands.
"""
import config
from dutch.lesson import DutchLesson
from learnx import audio_builder
from learnx.models import DialogueLine

# Speaker A -> ALEX voice, Speaker B -> MAYA voice (Dutch voices injected below).
_SPEAKER = {"A": "ALEX", "B": "MAYA"}
_DUTCH_VOICES = {"ALEX": config.DUTCH_VOICE_ALEX, "MAYA": config.DUTCH_VOICE_MAYA}
_DUTCH_RATES = {"ALEX": config.DUTCH_TTS_RATE, "MAYA": config.DUTCH_TTS_RATE}


def to_lines(lesson: DutchLesson) -> list[DialogueLine]:
    """Ordered TTS lines: each new word (+ its example sentence) read first, then
    the dialogue. Only the Dutch text is voiced — it is a listening exercise."""
    by_id = {s["id"]: s for s in lesson.sentences}
    lines: list[DialogueLine] = []
    for w in lesson.new_words:
        lines.append(DialogueLine(speaker="ALEX", text=w["nl"], unit_number=0))
        s = by_id.get(w["id"])
        if s and s.get("nl"):
            lines.append(DialogueLine(speaker="MAYA", text=s["nl"], unit_number=0))
    for d in lesson.dialogue:
        speaker = _SPEAKER.get(d["speaker"], "ALEX")
        lines.append(DialogueLine(speaker=speaker, text=d["nl"], unit_number=1))
    return [ln for ln in lines if ln.text.strip()]


async def build(lesson: DutchLesson, out_path: str) -> None:
    """Render the Dutch lesson MP3 to `out_path` (async; call via asyncio.run)."""
    lines = to_lines(lesson)
    if not lines:
        raise ValueError("No Dutch lines to render")
    await audio_builder.build(lines, out_path, voices=_DUTCH_VOICES, rates=_DUTCH_RATES)
