"""Tests for the cross-device progress scorecard derived from SR memory."""
from dutch.progress import build_progress


def _memory():
    return {
        "cefr": "A2",
        "streak": 4,
        "words": {"w1": {}, "w2": {}, "w3": {}},
        "recall": [
            {"date": "2026-06-11", "reported": "2026-06-12",
             "right": ["a", "b", "c"], "wrong": ["d"]},
            {"date": "2026-06-10", "reported": "2026-06-12",
             "right": ["x", "y"], "wrong": []},
        ],
    }


def test_build_progress_per_day_scores_sorted_by_date():
    p = build_progress(_memory())
    assert [d["date"] for d in p["days"]] == ["2026-06-10", "2026-06-11"]  # oldest first
    day = {d["date"]: d for d in p["days"]}
    assert day["2026-06-11"] == {"date": "2026-06-11", "reported": "2026-06-12",
                                 "right": 3, "wrong": 1}
    assert day["2026-06-10"]["right"] == 2 and day["2026-06-10"]["wrong"] == 0


def test_build_progress_headline_stats():
    p = build_progress(_memory())
    assert p["cefr"] == "A2"
    assert p["streak"] == 4
    assert p["words_tracked"] == 3


def test_build_progress_empty_memory_is_safe():
    p = build_progress({})
    assert p == {"cefr": "", "streak": 0, "words_tracked": 0, "days": []}


def test_build_progress_skips_entries_without_a_date():
    p = build_progress({"recall": [{"right": ["a"], "wrong": []}]})  # no date -> dropped
    assert p["days"] == []
