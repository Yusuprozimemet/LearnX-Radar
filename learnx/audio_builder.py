"""TTS render + assemble — ported/trimmed from LearnX-CLI (tutor/audio/).

Renders each dialogue line to speech with edge-tts (no API key), concatenates
with natural silence gaps, and exports ONE lesson MP3. Trimmed: no per-unit
files, no timing.json — the radar needs a single MP3 and nothing else.

This is the one sync->async crossing point: main.py calls
asyncio.run(audio_builder.build(lines, out_path)).
"""
import asyncio
import logging
import os
import shutil
from pathlib import Path

import edge_tts
from pydub import AudioSegment

from learnx.constants import (
    RATE_ALEX,
    RATE_MAYA,
    SILENCE_BREATH_MS,
    SILENCE_TURN_MS,
    SILENCE_UNIT_MS,
    TTS_SEMAPHORE_LIMIT,
    VOICE_ALEX,
    VOICE_MAYA,
)
from learnx.models import DialogueLine, RenderedSegment

log = logging.getLogger(__name__)

_VOICE = {"ALEX": VOICE_ALEX, "MAYA": VOICE_MAYA}
_RATE = {"ALEX": RATE_ALEX, "MAYA": RATE_MAYA}


async def build(
    lines: list[DialogueLine],
    out_path: str,
    *,
    voices: dict[str, str] | None = None,
    rates: dict[str, str] | None = None,
) -> None:
    """Render `lines` to one MP3. `voices`/`rates` (keyed by speaker) override the
    default English co-host map — the Dutch track passes its nl-NL voices here; dev
    callers pass nothing and get the unchanged behaviour."""
    if not lines:
        raise ValueError("No dialogue lines to render")
    voices = voices or _VOICE
    rates = rates or _RATE
    tmp_dir = Path(out_path).parent / ".tts_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    try:
        segments = await _render_all(lines, str(tmp_dir), voices, rates)
        _assemble(segments, out_path)
        log.info("Audio saved: %s", out_path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


async def _render_all(
    lines: list[DialogueLine], tmp_dir: str, voices: dict[str, str], rates: dict[str, str]
) -> list[RenderedSegment]:
    semaphore = asyncio.Semaphore(TTS_SEMAPHORE_LIMIT)
    results: list[RenderedSegment | None] = [None] * len(lines)

    async def render_one(idx: int, line: DialogueLine) -> None:
        async with semaphore:
            results[idx] = await _render_segment(line, tmp_dir, idx, voices, rates)

    await asyncio.gather(*[render_one(i, ln) for i, ln in enumerate(lines)])
    return [r for r in results if r is not None]


async def _render_segment(
    line: DialogueLine, out_dir: str, idx: int, voices: dict[str, str], rates: dict[str, str]
) -> RenderedSegment:
    voice = voices.get(line.speaker, VOICE_ALEX)
    rate = rates.get(line.speaker, RATE_ALEX)
    out_path = str(Path(out_dir) / f"seg_{idx:04d}.mp3")

    communicate = edge_tts.Communicate(line.text, voice, rate=rate)
    await communicate.save(out_path)
    if os.path.getsize(out_path) == 0:
        raise RuntimeError(f"TTS produced empty audio for line {idx}: {line.text[:60]}")

    duration_ms = len(AudioSegment.from_mp3(out_path))
    return RenderedSegment(line=line, audio_path=out_path, duration_ms=duration_ms)


def _assemble(segments: list[RenderedSegment], out_path: str) -> None:
    full = AudioSegment.empty()
    prev_speaker: str | None = None
    prev_unit: int | None = None

    for seg in segments:
        gap = _gap_ms(prev_speaker, prev_unit, seg.line)
        if gap:
            full += AudioSegment.silent(duration=gap)
        full += AudioSegment.from_mp3(seg.audio_path)
        prev_speaker, prev_unit = seg.line.speaker, seg.line.unit_number

    full.export(out_path, format="mp3")
    log.info("Assembled %d segments -> %s (%.1fs)", len(segments), out_path, len(full) / 1000)


def _gap_ms(prev_speaker: str | None, prev_unit: int | None, line: DialogueLine) -> int:
    """Silence before this line: none at the very start, longest between units."""
    if prev_speaker is None:
        return 0
    if prev_unit != line.unit_number:
        return SILENCE_UNIT_MS
    if prev_speaker != line.speaker:
        return SILENCE_TURN_MS
    return SILENCE_BREATH_MS
