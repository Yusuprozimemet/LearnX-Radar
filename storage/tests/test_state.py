"""Offline tests for state I/O — redirect file paths to tmp, no real writes."""
import json
from datetime import date, timedelta

from storage import state


def _iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def test_load_seen_migrates_legacy_list_to_empty_map(tmp_path, monkeypatch):
    # Pre-windowing files were a bare list of IDs with no dates; nothing to window
    # on, so they migrate to an empty map (a safe one-time reset — see load_seen).
    f = tmp_path / "seen.json"
    f.write_text(json.dumps(["gh:foo/bar", "hn:1"]), encoding="utf-8")
    monkeypatch.setattr(state, "SEEN_FILE", f)
    assert state.load_seen() == {}


def test_filter_new_suppresses_recent_but_lets_expired_resurface(monkeypatch):
    monkeypatch.setattr(state, "SEEN_TTL_DAYS", 14)
    seen = {"gh:recent": _iso(1), "gh:expired": _iso(15)}
    items = [{"id": "gh:recent"}, {"id": "gh:expired"}, {"id": "dev:brand-new"}]
    out = [i["id"] for i in state.filter_new(items, seen)]
    assert out == ["gh:expired", "dev:brand-new"]  # recent gone, expired+new pass


def test_mark_seen_stamps_today_in_place():
    seen = {"old": _iso(5)}
    state.mark_seen(seen, ["a", "b"])
    assert seen["a"] == date.today().isoformat()
    assert seen["b"] == date.today().isoformat()
    assert seen["old"] == _iso(5)  # untouched


def test_save_seen_prunes_expired_entries(tmp_path, monkeypatch):
    f = tmp_path / "seen.json"
    monkeypatch.setattr(state, "SEEN_FILE", f)
    monkeypatch.setattr(state, "SEEN_TTL_DAYS", 14)
    state.save_seen({"keep": _iso(2), "drop": _iso(20)})
    written = json.loads(f.read_text(encoding="utf-8"))
    assert "keep" in written and "drop" not in written


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


# A multi-source run with high scores vs a thin dev.to-only re-run (all 0.5).
_RICH = [
    {"skill": "Kafka", "score": 1.5, "sources": ["HN Hiring", "dev.to"]},
    {"skill": "Rust", "score": 1.0, "sources": ["GitHub Trending"]},
]
_THIN = [
    {"skill": "Cat plots", "score": 0.5, "sources": ["dev.to"]},
    {"skill": "Emoji filtering", "score": 0.5, "sources": ["dev.to"]},
]


def test_last_scored_thin_rerun_does_not_clobber_rich_same_day(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "LAST_SCORED_FILE", tmp_path / "ls.json")
    state.save_last_scored(_RICH, today_skill="Kafka")
    state.save_last_scored(_THIN, today_skill="Cat plots")  # thinner re-run
    loaded = state.load_last_scored()
    assert loaded["today_skill"] == "Kafka"  # the rich board is kept
    assert [s["skill"] for s in loaded["scored"]] == ["Kafka", "Rust"]


def test_last_scored_richer_rerun_replaces_thin_same_day(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "LAST_SCORED_FILE", tmp_path / "ls.json")
    state.save_last_scored(_THIN, today_skill="Cat plots")  # thin first
    state.save_last_scored(_RICH, today_skill="Kafka")      # richer wins
    assert state.load_last_scored()["today_skill"] == "Kafka"


def test_last_scored_new_day_overwrites_even_if_thin(tmp_path, monkeypatch):
    f = tmp_path / "ls.json"
    monkeypatch.setattr(state, "LAST_SCORED_FILE", f)
    # Yesterday's rich ranking, persisted with a stale date.
    f.write_text(
        json.dumps({"updated": _iso(1), "today_skill": "Kafka", "scored": _RICH}),
        encoding="utf-8",
    )
    state.save_last_scored(_THIN, today_skill="Cat plots")  # a new day always writes
    assert state.load_last_scored()["today_skill"] == "Cat plots"


def test_trending_history_thin_rerun_does_not_clobber_rich(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "HISTORY_FILE", tmp_path / "h.json")
    state.save_trending_history(_RICH, today_skill="Kafka")
    state.save_trending_history(_THIN, today_skill="Cat plots")  # thinner re-run
    today = date.today().isoformat()
    entry = state.load_trending_history()[today]
    assert entry["today_skill"] == "Kafka"  # richer day is preserved


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


def test_slugify_makes_unique_safe_names():
    assert state.slugify("Kafka consumer groups") == "kafka-consumer-groups"
    assert state.slugify("C# / .NET") == "c-net"
    assert state.slugify("") == "lesson"  # never empty (used in filenames)
    # distinct skills on the same day yield distinct audio filenames (the bug fix)
    a = f"lesson-20260531-{state.slugify('Airbyte')}.mp3"
    b = f"lesson-20260531-{state.slugify('Kafka consumer groups')}.mp3"
    assert a != b


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
