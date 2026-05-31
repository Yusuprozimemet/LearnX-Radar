"""Offline tests for state I/O — redirect file paths to tmp, no real writes."""
from datetime import date

from storage import state


def test_last_scored_roundtrip_and_trim(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "LAST_SCORED_FILE", tmp_path / "ls.json")
    monkeypatch.setattr(state, "LAST_SCORED_KEEP", 3)

    scored = [{"skill": f"S{i}", "score": float(i)} for i in range(10)]
    state.save_last_scored(scored, today_skill="S9")

    loaded = state.load_last_scored()
    assert loaded["today_skill"] == "S9"
    assert loaded["updated"] == date.today().isoformat()
    assert [s["skill"] for s in loaded["scored"]] == ["S0", "S1", "S2"]  # trimmed to 3


def test_load_last_scored_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "LAST_SCORED_FILE", tmp_path / "nope.json")
    assert state.load_last_scored() == {"today_skill": None, "scored": []}


def test_record_lesson_stores_audio_and_summary():
    memory = {"skills": {}}
    state.record_lesson(
        memory, "Kafka", title="Kafka", difficulty="beginner",
        summary="streaming", audio="lesson-20260530.mp3",
    )
    entry = memory["skills"]["Kafka"]
    assert entry["times_taught"] == 1
    assert entry["summary"] == "streaming"
    assert entry["lessons"][-1]["audio"] == "lesson-20260530.mp3"


def test_previous_lesson_none_when_empty():
    assert state.previous_lesson({"version": 1, "skills": {}}) is None


def test_previous_lesson_is_most_recent_across_skills():
    memory = {"skills": {
        "Kafka": {"lessons": [{"date": "2026-05-20", "brief": "k.md"}]},
        "Rust": {"lessons": [
            {"date": "2026-05-22", "brief": "r1.md"},
            {"date": "2026-05-29", "brief": "r2.md"},  # newest overall
        ]},
    }}
    prev = state.previous_lesson(memory)
    assert prev["skill"] == "Rust"
    assert prev["brief"] == "r2.md"
    assert prev["date"] == "2026-05-29"
