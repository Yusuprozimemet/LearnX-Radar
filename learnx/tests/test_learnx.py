"""Offline tests for the audio pipeline. No network, no TTS — the LLM stages use
a canned chat_fn and the audio logic is tested via its pure silence-gap helper."""
import json

from learnx import audio_builder, curriculum, dialogue, sanitizer
from learnx.constants import (
    MIN_UNIT_WORDS,
    OVERHEAD_WORDS,
    SILENCE_BREATH_MS,
    SILENCE_TURN_MS,
    SILENCE_UNIT_MS,
    WPM,
)
from learnx.models import DialogueLine


# --- curriculum --------------------------------------------------------------

def _canned_units(n=3):
    return json.dumps([
        {"concept": f"C{i}", "complexity": 2, "key_facts": ["f1", "f2"],
         "analogy": "like a box", "misconception": "not magic", "memory_hook": "remember C"}
        for i in range(n)
    ])


def test_curriculum_builds_units_and_budgets():
    units = curriculum.plan("brief text", "DuckDB", duration_min=5,
                            chat_fn=lambda *a, **k: _canned_units(3))
    assert len(units) == 3
    assert [u.unit for u in units] == [1, 2, 3]
    # equal complexity → equal budgets summing near the word budget
    total = 5 * WPM - OVERHEAD_WORDS
    assert all(u.word_budget >= MIN_UNIT_WORDS for u in units)
    assert abs(sum(u.word_budget for u in units) - total) <= len(units)


def test_curriculum_injects_difficulty_context():
    from learnx.constants import DIFFICULTY_CONTEXT
    captured = {}

    def fake(messages, **k):
        captured["prompt"] = messages[0]["content"]
        return _canned_units(2)

    curriculum.plan("brief", "DuckDB", difficulty="advanced", chat_fn=fake)
    assert "advanced" in captured["prompt"]
    assert DIFFICULTY_CONTEXT["advanced"][:40] in captured["prompt"]


def test_curriculum_clamps_complexity_and_caps_units():
    raw = json.dumps([{"concept": f"C{i}", "complexity": 9} for i in range(20)])
    units = curriculum.plan("b", "T", chat_fn=lambda *a, **k: raw)
    assert len(units) <= 6  # MAX_UNITS
    assert all(1 <= u.complexity <= 3 for u in units)


# --- dialogue ----------------------------------------------------------------

def test_dialogue_orders_intro_units_outro():
    from learnx.models import TeachingUnit
    units = [TeachingUnit(unit=1, concept="C1", word_budget=200),
             TeachingUnit(unit=2, concept="C2", word_budget=200)]

    def fake(messages, **k):
        # echo a valid two-line exchange so every section yields lines
        return "ALEX: Hello there.\nMAYA: Yes indeed."

    lines = dialogue.generate(units, "DuckDB", hook="why", chat_fn=fake)
    seen = [ln.unit_number for ln in lines]
    # intro(0) first, outro(-1) last, units 1 and 2 in between
    assert seen[0] == 0 and seen[-1] == -1
    assert set(seen) == {0, 1, 2, -1}
    assert {ln.speaker for ln in lines} == {"ALEX", "MAYA"}


def test_dialogue_parse_ignores_unlabeled_and_other_speakers():
    raw = "ALEX: One.\n(stage note)\nSAM: nope.\nMAYA - Two.\nrandom"
    lines = dialogue._parse(raw, unit_number=1)
    assert [(l.speaker, l.text) for l in lines] == [("ALEX", "One."), ("MAYA", "Two.")]


# --- sanitizer ---------------------------------------------------------------

def test_sanitizer_speaks_symbols():
    assert "not equal to" in sanitizer.apply("a != b")
    assert "arrow" in sanitizer.apply("x => y")
    assert "`" not in sanitizer.apply("use `foo` here")
    assert "for example" in sanitizer.apply("e.g. this")
    assert sanitizer.apply("a  &&  b") == "a and b"


# --- audio assembly (pure helper) -------------------------------------------

def test_silence_gap_logic():
    g = audio_builder._gap_ms
    start = DialogueLine("ALEX", "hi", 1)
    assert g(None, None, start) == 0                          # very first line
    assert g("ALEX", 1, DialogueLine("ALEX", "x", 1)) == SILENCE_BREATH_MS
    assert g("ALEX", 1, DialogueLine("MAYA", "x", 1)) == SILENCE_TURN_MS
    assert g("MAYA", 1, DialogueLine("ALEX", "x", 2)) == SILENCE_UNIT_MS
