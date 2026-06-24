"""Offline tests for the Status-tab run history (v11 day 40): pure entry builder
plus the rolling, capped IO (paths redirected to tmp, no real writes)."""
from datetime import date, timedelta

from storage import run_history, state


def _iso(days_ago: int) -> str:
    return (date.today() - timedelta(days=days_ago)).isoformat()


def test_build_entry_flattens_stages_and_carries_no_error_text():
    entry = run_history.build_entry(
        stages={"scrape": True, "delivery": False},
        sources={"reddit": 5, "lobsters": 0},
        llm={"nvidia_timeouts": 3, "breaker_tripped": True},
        delivery={"telegram": True, "email": False},
        duration_s=12.34,
    )
    assert entry["stages"] == {"scrape": "ok", "delivery": "fail"}
    assert entry["ok"] is False  # a failed stage makes the run not-ok
    assert entry["sources"] == {"reddit": 5, "lobsters": 0}
    assert entry["llm"] == {"nvidia_timeouts": 3, "breaker_tripped": True}
    assert entry["delivery"] == {"telegram": True, "email": False}
    assert entry["duration_s"] == 12.3
    # Only verdicts are stored — never the exception strings (safe on the public page).
    assert "fail" in entry["stages"].values()
    blob = repr(entry)
    assert "Traceback" not in blob and "Exception" not in blob


def test_build_entry_all_ok_when_every_stage_passes():
    entry = run_history.build_entry(stages={"scrape": True, "dutch": True}, sources={})
    assert entry["ok"] is True
    assert entry["date"] == date.today().isoformat()


def test_save_run_history_overwrites_day_and_caps(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "RUN_HISTORY_FILE", tmp_path / "run_history.json")
    monkeypatch.setattr(state, "RUN_HISTORY_KEEP_DAYS", 3)

    # Five days of entries; only the newest 3 survive the cap.
    for d in range(5):
        state.save_run_history(
            run_history.build_entry(stages={"scrape": True}, sources={},
                                    when=date.today() - timedelta(days=d))
        )
    history = state.load_run_history()
    assert len(history) == 3
    assert set(history) == {_iso(0), _iso(1), _iso(2)}

    # Re-running the same day replaces that day's entry rather than duplicating it.
    state.save_run_history(
        run_history.build_entry(stages={"scrape": False}, sources={}, when=date.today())
    )
    assert state.load_run_history()[_iso(0)]["stages"]["scrape"] == "fail"


def test_load_run_history_missing_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "RUN_HISTORY_FILE", tmp_path / "absent.json")
    assert state.load_run_history() == {}
