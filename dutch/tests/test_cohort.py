"""Tests for the anonymous multi-user learning aggregate (v11 day 40)."""
from datetime import date, timedelta

from dutch.cohort import build_cohort

TODAY = date(2026, 6, 24)


def _recent(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


def _learner(cefr, recall, words):
    return {"cefr": cefr, "recall": recall, "words": words}


def _cohort():
    return [
        _learner(
            "A2",
            [{"date": _recent(2), "reported": _recent(2),
              "right": ["a", "b"], "wrong": ["zonnebloem"]}],
            {"zonnebloem": {"recall_wrong": 2}, "a": {"recall_wrong": 0}},
        ),
        _learner(
            "B1",
            [{"date": _recent(20), "reported": _recent(20),
              "right": ["a"], "wrong": ["zonnebloem", "fiets"]}],
            {"zonnebloem": {"recall_wrong": 1}, "fiets": {"recall_wrong": 3}},
        ),
        _learner("A2", [], {}),  # enrolled but never practiced
    ]


def test_cohort_counts_and_activity_windows():
    c = build_cohort(_cohort(), today=TODAY)
    assert c["learners_total"] == 3
    assert c["active_7d"] == 1   # only the learner who reported 2 days ago
    assert c["active_30d"] == 2  # the 20-day-ago learner counts in the 30d window


def test_cohort_recall_is_pooled_over_30_days():
    c = build_cohort(_cohort(), today=TODAY)
    rec = c["cohort_recall_30d"]
    # Both reporters fall inside 30d (2 and 20 days ago): pooled 3 right / 3 wrong = 50%.
    assert (rec["right"], rec["wrong"], rec["pct"]) == (3, 3, 50)


def test_cohort_recall_excludes_reports_older_than_30_days():
    learner = _learner(
        "A2",
        [{"date": _recent(45), "reported": _recent(45), "right": ["a", "b"], "wrong": []}],
        {},
    )
    c = build_cohort([learner], today=TODAY)
    assert c["cohort_recall_30d"] == {"right": 0, "wrong": 0, "pct": None}
    assert c["active_30d"] == 0  # last active 45 days ago → outside the window


def test_cohort_cefr_distribution_and_hardest_words():
    c = build_cohort(_cohort(), today=TODAY)
    assert c["cefr_distribution"] == {"A2": 2, "B1": 1}
    hardest = c["hardest_words"]
    # zonnebloem is failed by two learners -> ranks above fiets (one learner, 3 fails).
    assert hardest[0]["id"] == "zonnebloem"
    assert hardest[0]["learners_failing"] == 2 and hardest[0]["fails"] == 3
    ids = {w["id"] for w in hardest}
    assert "fiets" in ids and "a" not in ids  # only words with a failure appear


def test_cohort_output_carries_no_learner_identity():
    blob = repr(build_cohort(_cohort(), today=TODAY))
    assert "chat" not in blob.lower() and "token" not in blob.lower()


def test_cohort_single_member_is_safe():
    c = build_cohort([_learner("A2", [], {})], today=TODAY)
    assert c["learners_total"] == 1
    assert c["cohort_recall_30d"]["pct"] is None
    assert c["hardest_words"] == []
