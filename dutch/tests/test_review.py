"""Tests for the per-user cross-day review builder (multi-user Phase 1)."""
import json
from datetime import date

from dutch import review as dutch_review

_BANK = [
    {"id": "afspraak", "nl": "de afspraak", "en": "the appointment"},
    {"id": "huis", "nl": "het huis", "en": "the house"},
    {"id": "trein", "nl": "de trein", "en": "the train"},
]


def _archive(tmp_path):
    lessons = tmp_path / "lessons"
    lessons.mkdir()
    (lessons / "dutch-2026-05-30.json").write_text(
        json.dumps({
            "audio_url": "http://cdn/dutch-20260530.mp3",
            "report": {"words": [{"id": "afspraak", "form": "afspraak"}]},
            "segments": [
                {"nl": "Ik heb een afspraak.", "en": "I have an appointment.",
                 "start_ms": 1000, "end_ms": 2000},
            ],
        }),
        encoding="utf-8",
    )
    return lessons


def test_build_distills_due_words_with_archive_drill(tmp_path):
    # afspraak is due (past), huis is due later, trein has no SR entry at all.
    memory = {"words": {"afspraak": {"due": "2026-06-01"}, "huis": {"due": "2026-07-01"}}}
    out = dutch_review.build(memory, _archive(tmp_path), _BANK, today=date(2026, 6, 5))
    assert out["generated"] == "2026-06-05"
    assert out["ids"] == ["afspraak"]            # only the due word, not huis/trein
    item = out["items"][0]
    assert item["en"] == "the appointment" and item["form"] == "afspraak"
    # example sentence + audio span pulled from the day it was taught
    assert item["sentence_nl"] == "Ik heb een afspraak."
    assert item["audio_url"].endswith("dutch-20260530.mp3")
    assert item["start_ms"] == 1000 and item["end_ms"] == 2000


def test_build_gloss_only_when_no_archive_example(tmp_path):
    """A due word with no archived sentence still ships as a gloss-only drill."""
    memory = {"words": {"huis": {"due": "2026-06-01"}}}
    out = dutch_review.build(memory, _archive(tmp_path), _BANK, today=date(2026, 6, 5))
    assert out["ids"] == ["huis"]
    assert out["items"][0]["nl"] == "het huis"
    assert "sentence_nl" not in out["items"][0]   # no archive match -> no drill keys


def test_build_caps_and_skips_unknown_ids(tmp_path):
    memory = {"words": {
        "afspraak": {"due": "2026-06-01"},
        "huis": {"due": "2026-06-01"},
        "gone": {"due": "2026-06-01"},   # not in the frozen bank -> skipped
    }}
    out = dutch_review.build(memory, _archive(tmp_path), _BANK, today=date(2026, 6, 5),
                            max_items=1)
    assert out["ids"] == ["afspraak"]    # capped to 1; 'gone' would be skipped anyway


def test_build_empty_when_nothing_due(tmp_path):
    out = dutch_review.build({"words": {}}, _archive(tmp_path), _BANK, today=date(2026, 6, 5))
    assert out["ids"] == [] and out["items"] == []
