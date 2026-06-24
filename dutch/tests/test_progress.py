"""Tests for the cross-device progress scorecard derived from SR memory."""
from datetime import date

from dutch.progress import advance_cefr, build_progress


def _reports(n, *, right, wrong, start=date(2026, 6, 1)):
    """n recall reports on consecutive days, each with `right`/`wrong` word counts."""
    return [
        {"date": (start.replace(day=start.day + i)).isoformat(),
         "right": [f"r{i}_{j}" for j in range(right)],
         "wrong": [f"w{i}_{j}" for j in range(wrong)]}
        for i in range(n)
    ]


def test_advance_cefr_promotes_when_recall_clears_the_bar():
    # 6 reports, 5 right / 0 wrong each = 30 attempts at 100% -> clears A2.
    memory = {"cefr": "A2", "cefr_since": None, "recall": _reports(6, right=5, wrong=0)}
    level, advanced = advance_cefr(memory, date(2026, 6, 30))
    assert advanced and level == "A2+"
    assert memory["cefr"] == "A2+" and memory["cefr_since"] == "2026-06-30"


def test_advance_cefr_holds_when_recall_too_low():
    # 6 reports, 3 right / 3 wrong = 50% -> below the 0.85 bar.
    memory = {"cefr": "A2", "cefr_since": None, "recall": _reports(6, right=3, wrong=3)}
    level, advanced = advance_cefr(memory, date(2026, 6, 30))
    assert not advanced and level == "A2" and memory["cefr"] == "A2"


def test_advance_cefr_holds_without_enough_data():
    # High recall but only 2 reports / 10 words -> not enough to trust the rate.
    memory = {"cefr": "A2", "cefr_since": None, "recall": _reports(2, right=5, wrong=0)}
    _level, advanced = advance_cefr(memory, date(2026, 6, 30))
    assert not advanced


def test_advance_cefr_caps_at_b1():
    memory = {"cefr": "B1", "cefr_since": None, "recall": _reports(10, right=5, wrong=0)}
    level, advanced = advance_cefr(memory, date(2026, 6, 30))
    assert not advanced and level == "B1"


def test_advance_cefr_only_counts_reports_since_current_rung():
    # Plenty of old high-recall reports, but cefr_since postdates them -> they don't count.
    memory = {"cefr": "A2", "cefr_since": "2026-06-20",
              "recall": _reports(6, right=5, wrong=0, start=date(2026, 6, 1))}
    _level, advanced = advance_cefr(memory, date(2026, 6, 30))
    assert not advanced


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
