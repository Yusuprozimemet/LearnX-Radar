"""Compose the Delft trainer's lesson JSON (v9 day 32).

The daily run writes this payload to storage/dutch_lesson.json (committed by the
workflow); the static dashboard/dutch.html page on GitHub Pages fetches it and runs
the Delft phases interactively. Pure composition — no I/O, no LLM: everything here
was already produced by the lesson build and the audio render.
"""
from datetime import date

import config
from dutch import cloze
from dutch.lesson import DutchLesson

# audio_builder unit numbers -> Delft block letters (see dutch/audio.to_lines):
# 0 = vocabulary, 1 = dialogue sentence-by-sentence, 2 = dialogue straight through.
_BLOCKS = {0: "A", 1: "B", 2: "C"}


def build_payload(
    lesson: DutchLesson,
    timings: list[dict],
    audio_filename: str,
    when: date | None = None,
) -> dict:
    """The trainer page's lesson JSON: text + translations + cloze + a seek map.

    `timings` come from the audio render ({speaker, text, unit, start_ms, end_ms}
    per spoken line); each becomes a segment with its Delft block letter and the
    translation looked up by exact Dutch text (word glosses, example sentences,
    dialogue lines all carry one). `block_c` is the straight-through dialogue's
    span — what the one-chance exercise plays.
    """
    en_by_nl: dict[str, str] = {}
    for w in lesson.new_words + lesson.review_words:
        if w.get("nl"):
            en_by_nl[w["nl"]] = w.get("en", "")
    for s in lesson.sentences:
        if s.get("nl"):
            en_by_nl[s["nl"]] = s.get("en", "")
    for d in lesson.dialogue:
        if d.get("nl"):
            en_by_nl[d["nl"]] = d.get("en", "")

    segments = [
        {
            "block": _BLOCKS.get(t.get("unit"), "A"),
            "speaker": t.get("speaker", ""),
            "nl": t.get("text", ""),
            "en": en_by_nl.get(t.get("text", ""), ""),
            "start_ms": t.get("start_ms", 0),
            "end_ms": t.get("end_ms", 0),
        }
        for t in timings
    ]

    def span(block: str) -> dict | None:
        rows = [s for s in segments if s["block"] == block]
        if not rows:
            return None
        return {"start_ms": rows[0]["start_ms"], "end_ms": rows[-1]["end_ms"]}

    return {
        "date": (when or date.today()).isoformat(),
        "theme": lesson.theme,
        "cefr": lesson.cefr,
        "audio_url": f"{config.RELEASES_AUDIO_BASE}/{audio_filename}",
        "new_words": lesson.new_words,
        "sentences": lesson.sentences,
        "dialogue": lesson.dialogue,
        # Gatentekst: one blank per NEW word across the whole text (same exercise
        # as the printed PDF section).
        "cloze": cloze.extract(lesson.new_words, lesson.sentences, lesson.dialogue),
        # Luistertoets: per dialogue line, EVERY new+review word blanked — hear the
        # sentence once, then produce its words. Indexed 1:1 with block C segments.
        "luistertoets": cloze.sentence_blanks(
            lesson.new_words + lesson.review_words, lesson.dialogue
        ),
        "segments": segments,
        "block_b": span("B"),  # sentence -> repeat pause -> sentence again (Delft step 3)
        "block_c": span("C"),  # the dialogue straight through (Delft steps 2/4)
    }
