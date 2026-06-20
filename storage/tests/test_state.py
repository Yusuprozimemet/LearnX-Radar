"""Offline tests for state I/O — redirect file paths to tmp, no real writes."""
import json
from datetime import date, timedelta

from storage import state


def _iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def test_learned_aliases_roundtrip_and_merge(tmp_path, monkeypatch):
    import config
    f = tmp_path / "skill_aliases.json"
    monkeypatch.setattr(state, "LEARNED_ALIASES_FILE", f)
    state.save_learned_aliases({"autonomous ai agents": "ai agents"})
    assert state.load_learned_aliases() == {"autonomous ai agents": "ai agents"}

    # apply_learned_aliases merges into config without clobbering hand-written entries.
    monkeypatch.setattr(config, "SKILL_ALIASES", {"k8s": "kubernetes"})
    added = state.apply_learned_aliases()
    assert added == 1
    assert config.SKILL_ALIASES["autonomous ai agents"] == "ai agents"
    assert config.SKILL_ALIASES["k8s"] == "kubernetes"


def test_learned_aliases_missing_file_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "LEARNED_ALIASES_FILE", tmp_path / "nope.json")
    assert state.load_learned_aliases() == {}
    assert state.apply_learned_aliases() == 0


def test_alias_denylist_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "ALIAS_DENYLIST_FILE", tmp_path / "deny.json")
    assert state.load_alias_denylist() == set()        # missing file -> empty
    pairs = {frozenset(("claude code", "claude")), frozenset(("a", "b"))}
    state.save_alias_denylist(pairs)
    assert state.load_alias_denylist() == pairs        # survives the roundtrip


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


def test_record_lesson_rating_stamps_by_date_and_supersedes():
    memory = {"skills": {
        "Kafka": {"lessons": [{"date": "2026-06-08", "title": "Kafka"}]},
        "Rust": {"lessons": [{"date": "2026-06-07", "title": "Rust"}]},
    }}
    assert state.record_lesson_rating(memory, "2026-06-08", 4) == 1
    assert memory["skills"]["Kafka"]["lessons"][0]["rating"] == 4
    assert "rating" not in memory["skills"]["Rust"]["lessons"][0]
    # a re-tap is an opinion change — the new rating overwrites the old one
    assert state.record_lesson_rating(memory, "2026-06-08", 2) == 1
    assert memory["skills"]["Kafka"]["lessons"][0]["rating"] == 2
    # no lesson on that date -> nothing stamped
    assert state.record_lesson_rating(memory, "2026-06-01", 5) == 0


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


# --- dutch_memory.json : Dutch vocab spaced repetition (v5) -------------------

def test_dutch_memory_roundtrip_and_default(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "DUTCH_MEMORY_FILE", tmp_path / "nope.json")
    fresh = state.load_dutch_memory()
    assert fresh["version"] == 1 and fresh["words"] == {} and fresh["streak"] == 0

    f = tmp_path / "dutch.json"
    monkeypatch.setattr(state, "DUTCH_MEMORY_FILE", f)
    state.save_dutch_memory({"version": 1, "cefr": "A2", "words": {"a": {"reps": 1}}})
    loaded = state.load_dutch_memory()
    assert loaded["words"]["a"]["reps"] == 1
    assert loaded["streak"] == 0  # missing keys backfilled to the default shape


def test_dutch_memory_corrupt_returns_default(tmp_path, monkeypatch):
    f = tmp_path / "dutch.json"
    f.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(state, "DUTCH_MEMORY_FILE", f)
    assert state.load_dutch_memory()["words"] == {}


def test_dutch_due_words_only_due_oldest_first():
    today = date(2026, 6, 5)
    memory = {"words": {
        "due_old": {"due": "2026-06-01"},
        "due_today": {"due": "2026-06-05"},
        "later": {"due": "2026-06-20"},
    }}
    assert state.dutch_due_words(memory, today) == ["due_old", "due_today"]


def test_record_dutch_lesson_new_then_review_widens_interval():
    memory = state._default_dutch_memory()
    day1 = date(2026, 6, 1)
    state.record_dutch_lesson(memory, word_ids=["a"], theme="everyday", when=day1)
    a = memory["words"]["a"]
    assert a["reps"] == 1
    assert a["introduced"] == "2026-06-01"
    assert a["due"] == "2026-06-02"          # base interval = 1 day after first
    assert memory["streak"] == 1
    assert memory["last_words"] == ["a"]
    assert memory["lessons"][-1]["theme"] == "everyday"

    # consecutive next day, re-serving 'a' as review -> reps 2, wider interval
    day2 = date(2026, 6, 2)
    state.record_dutch_lesson(memory, word_ids=["a"], theme="tech", when=day2)
    a = memory["words"]["a"]
    assert a["reps"] == 2
    assert a["due"] > "2026-06-03"           # interval widened beyond 1 day
    assert memory["streak"] == 2             # consecutive day -> streak grows


def test_record_dutch_lesson_streak_resets_after_gap():
    memory = state._default_dutch_memory()
    state.record_dutch_lesson(memory, word_ids=["a"], theme="everyday", when=date(2026, 6, 1))
    state.record_dutch_lesson(memory, word_ids=["b"], theme="everyday", when=date(2026, 6, 5))
    assert memory["streak"] == 1  # gap of >1 day resets


# --- recall feedback into the scheduler (v9 day 33) ---------------------------

def test_record_dutch_recall_right_wrong_and_untrained():
    memory = state._default_dutch_memory()
    state.record_dutch_lesson(memory, word_ids=["a", "b", "c"], theme="everyday",
                              when=date(2026, 6, 1))
    state.record_dutch_lesson(memory, word_ids=["a", "b", "c"], theme="everyday",
                              when=date(2026, 6, 2))  # reps -> 2, interval widened

    applied = state.record_dutch_recall(memory, "2026-06-02", "10x",
                                        when=date(2026, 6, 3))
    assert applied == 2
    a, b, c = memory["words"]["a"], memory["words"]["b"], memory["words"]["c"]
    # right: counter up, scheduling untouched (exposure already widened it)
    assert a["recall_right"] == 1 and "recall_wrong" not in a
    assert a["reps"] == 2 and a["due"] == "2026-06-04"
    # wrong: forgotten card — reps back to 1, due = lesson date + base interval
    assert b["recall_wrong"] == 1
    assert b["reps"] == 1 and b["due"] == "2026-06-03"
    # 'x' (not trained): exposure-based scheduling stays the fallback
    assert "recall_right" not in c and "recall_wrong" not in c
    assert c["reps"] == 2
    # the report log feeds the dashboard's rolling recall rate
    log = memory["recall"][-1]
    assert log["date"] == "2026-06-02" and log["reported"] == "2026-06-03"
    assert log["right"] == ["a"] and log["wrong"] == ["b"]


def test_record_dutch_recall_unknown_date_and_duplicate_noop():
    memory = state._default_dutch_memory()
    state.record_dutch_lesson(memory, word_ids=["a"], theme="everyday", when=date(2026, 6, 1))

    assert state.record_dutch_recall(memory, "2026-05-30", "1") == 0  # no such lesson
    assert state.record_dutch_recall(memory, "2026-06-01", "1") == 1
    # duplicate tap on the deep link: first report wins, counters don't double
    assert state.record_dutch_recall(memory, "2026-06-01", "0") == 0
    a = memory["words"]["a"]
    assert a["recall_right"] == 1 and "recall_wrong" not in a
    assert len(memory["recall"]) == 1


def test_dutch_unsubmitted_streak_counts_newest_unfinished():
    memory = state._default_dutch_memory()
    for day in range(1, 6):  # 5 lessons delivered, none practiced yet
        state.record_dutch_lesson(memory, word_ids=["a"], theme="everyday",
                                  when=date(2026, 6, day))
    assert state.dutch_unsubmitted_streak(memory) == 5

    # Practice the most recent one -> streak resets to 0 (caught up at the top)
    state.record_dutch_recall(memory, "2026-06-05", "1", when=date(2026, 6, 6))
    assert state.dutch_unsubmitted_streak(memory) == 0

    # A new unfinished lesson on top -> counts only the consecutive run from newest
    state.record_dutch_lesson(memory, word_ids=["a"], theme="everyday",
                              when=date(2026, 6, 6))
    assert state.dutch_unsubmitted_streak(memory) == 1


def test_dutch_unsubmitted_streak_stops_at_first_finished():
    memory = state._default_dutch_memory()
    for day in range(1, 5):
        state.record_dutch_lesson(memory, word_ids=["a"], theme="everyday",
                                  when=date(2026, 6, day))
    # Finish an OLDER lesson (day 2); days 3 and 4 remain unfinished above it
    state.record_dutch_recall(memory, "2026-06-02", "1", when=date(2026, 6, 5))
    assert state.dutch_unsubmitted_streak(memory) == 2  # days 4 and 3, stops at day 2


def test_dutch_unsubmitted_streak_empty_when_no_lessons():
    assert state.dutch_unsubmitted_streak(state._default_dutch_memory()) == 0


def test_save_dutch_lesson_archives_dated_copy_and_index(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "DUTCH_LESSON_FILE", tmp_path / "dutch_lesson.json")
    monkeypatch.setattr(state, "DUTCH_LESSONS_DIR", tmp_path / "lessons")

    state.save_dutch_lesson({"date": "2026-06-10", "theme": "tech", "cefr": "A2"})
    state.save_dutch_lesson({"date": "2026-06-11", "theme": "everyday", "cefr": "A2"})
    # same-day re-run replaces that day's archive entry instead of duplicating it
    state.save_dutch_lesson({"date": "2026-06-11", "theme": "tech", "cefr": "A2"})

    latest = json.loads((tmp_path / "dutch_lesson.json").read_text(encoding="utf-8"))
    assert latest["date"] == "2026-06-11"
    archived = json.loads(
        (tmp_path / "lessons" / "dutch-2026-06-10.json").read_text(encoding="utf-8")
    )
    assert archived["theme"] == "tech"
    index = json.loads((tmp_path / "lessons" / "index.json").read_text(encoding="utf-8"))
    assert [e["date"] for e in index["lessons"]] == ["2026-06-10", "2026-06-11"]
    assert index["lessons"][1]["theme"] == "tech"


def test_save_dutch_lesson_without_date_skips_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "DUTCH_LESSON_FILE", tmp_path / "dutch_lesson.json")
    monkeypatch.setattr(state, "DUTCH_LESSONS_DIR", tmp_path / "lessons")
    state.save_dutch_lesson({"theme": "tech"})
    assert (tmp_path / "dutch_lesson.json").exists()
    assert not (tmp_path / "lessons").exists()
