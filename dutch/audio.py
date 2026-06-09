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
    """Ordered TTS lines. Delft layout (v9, default): Block A vocab and Block B
    dialogue play each sentence with a repeat pause and a self-check replay; Block C
    is the dialogue straight through (the "whole text" listen of Delft steps 2/4).
    Legacy v5 layout (words+dialogue, no pauses) behind DUTCH_DELFT_AUDIO=False.
    Only the Dutch text is voiced — it is a listening exercise."""
    if not config.DUTCH_DELFT_AUDIO:
        return _to_lines_legacy(lesson)
    factor = config.DUTCH_DELFT_PAUSE_FACTOR
    by_id = {s["id"]: s for s in lesson.sentences}
    lines: list[DialogueLine] = []
    # Block A (unit 0) — vocabulary: word -> sentence -> pause (repeat aloud)
    # -> sentence again (self-check). A word without a sentence gets the pause itself.
    for w in lesson.new_words:
        s = by_id.get(w["id"])
        if s and s.get("nl"):
            lines.append(DialogueLine(speaker="ALEX", text=w["nl"], unit_number=0))
            lines.append(DialogueLine(
                speaker="MAYA", text=s["nl"], unit_number=0, pause_after_factor=factor
            ))
            lines.append(DialogueLine(
                speaker="MAYA", text=s["nl"], unit_number=0, pause_after_factor=0.5
            ))
        else:
            lines.append(DialogueLine(
                speaker="ALEX", text=w["nl"], unit_number=0, pause_after_factor=factor
            ))
    # Block B (unit 1) — dialogue, sentence by sentence: line -> pause -> line again.
    for d in lesson.dialogue:
        speaker = _SPEAKER.get(d["speaker"], "ALEX")
        lines.append(DialogueLine(
            speaker=speaker, text=d["nl"], unit_number=1, pause_after_factor=factor
        ))
        lines.append(DialogueLine(
            speaker=speaker, text=d["nl"], unit_number=1, pause_after_factor=0.5
        ))
    # Block C (unit 2) — the dialogue straight through, natural turn gaps only.
    for d in lesson.dialogue:
        speaker = _SPEAKER.get(d["speaker"], "ALEX")
        lines.append(DialogueLine(speaker=speaker, text=d["nl"], unit_number=2))
    return [ln for ln in lines if ln.text.strip()]


def _to_lines_legacy(lesson: DutchLesson) -> list[DialogueLine]:
    """v5 layout: each new word (+ its example sentence), then the dialogue once."""
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


async def build(lesson: DutchLesson, out_path: str) -> list[dict]:
    """Render the Dutch lesson MP3 to `out_path` (async; call via asyncio.run).
    Returns per-line timings ({speaker, text, unit, start_ms, end_ms}) — the seek
    map the Delft trainer page uses to play one sentence at a time (v9 day 32)."""
    lines = to_lines(lesson)
    if not lines:
        raise ValueError("No Dutch lines to render")
    timings: list[dict] = []
    await audio_builder.build(
        lines, out_path, voices=_DUTCH_VOICES, rates=_DUTCH_RATES, timings_out=timings
    )
    return timings
