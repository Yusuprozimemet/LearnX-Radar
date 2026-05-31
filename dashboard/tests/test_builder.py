"""Offline tests for the dashboard renderer. Pure HTML, no network."""
from dashboard import builder


def _memory():
    return {
        "version": 1,
        "skills": {
            "Kafka consumer groups": {
                "times_taught": 1,
                "last_taught": "2026-05-29",
                "summary": "partitioned consumption",
                "lessons": [
                    {
                        "date": "2026-05-29",
                        "title": "Kafka consumer groups",
                        "difficulty": "beginner",
                        "summary": "partitioned consumption",
                        "audio": "lesson-20260529.mp3",
                    }
                ],
            }
        },
    }


def _scored():
    return [
        {"skill": "DuckDB", "score": 3.0, "demand_weight": 3.0, "frequency": 3,
         "sources": ["GitHub Trending", "dev.to", "Stack Overflow"], "evidence": "fast OLAP",
         "table_stakes": False},
        {"skill": "Kafka consumer groups", "score": 0.0, "demand_weight": 2.0, "frequency": 1,
         "sources": ["HN Hiring"], "evidence": "streaming", "table_stakes": False},
        {"skill": "Python", "score": 0.5, "demand_weight": 5.0, "frequency": 4,
         "sources": ["HN Hiring", "dev.to"], "evidence": "ubiquitous", "table_stakes": True},
    ]


def test_build_writes_all_sections(tmp_path):
    out = builder.build(_memory(), _scored(), today_skill="DuckDB", out_path=tmp_path / "d.html")
    html = out.read_text(encoding="utf-8")
    assert out.exists()
    for heading in ("Trending today", "Your coverage", "Gap highlights", "Lesson archive"):
        assert heading in html
    assert "DuckDB" in html and "🎧 today" in html        # today's pick marked
    assert "Kafka consumer groups" in html                # archive lists the lesson
    assert "<audio" not in html                            # metadata-only: no players


def test_radar_drawn_when_enough_scored_skills(tmp_path):
    scored = [
        {"skill": f"Skill{i}", "score": float(i + 1), "demand_weight": 1.0,
         "frequency": 1, "sources": ["dev.to"], "evidence": "x", "table_stakes": False}
        for i in range(4)
    ]
    html = builder.build(
        {"skills": {}}, scored, out_path=tmp_path / "d.html"
    ).read_text("utf-8")
    assert "<svg" in html and "Top trending skills radar" in html


def test_trending_date_picker_renders_each_day(tmp_path):
    history = {
        "2026-05-31": {"today_skill": "Airbyte", "scored": _scored()},
        "2026-05-30": {"today_skill": "DuckDB", "scored": _scored()},
    }
    html = builder.build(
        _memory(), out_path=tmp_path / "d.html", history=history
    ).read_text("utf-8")
    # A picker with both days, latest selected, and the embedded per-day fragments.
    assert "id='trend-date'" in html
    assert "May 31, 2026" in html and "May 30, 2026" in html
    assert "id='trend-data'" in html
    assert "<\\/table>" in html  # '</' escaped so the embedded HTML can't close the script


def test_single_day_has_no_picker(tmp_path):
    html = builder.build(
        _memory(), _scored(), today_skill="DuckDB", out_path=tmp_path / "d.html"
    ).read_text("utf-8")
    assert "id='trend-date'" not in html  # no dropdown until there are 2+ days


def test_archive_collapses_older_lessons(tmp_path):
    lessons = [
        {"date": f"2026-05-{10 + i:02d}", "title": f"Lesson {i}", "difficulty": "beginner",
         "summary": "s", "audio": ""}
        for i in range(8)
    ]
    mem = {"skills": {"X": {"times_taught": 8, "last_taught": "2026-05-17", "lessons": lessons}}}
    html = builder.build(mem, [], out_path=tmp_path / "d.html").read_text("utf-8")
    assert "<details>" in html and "Show 3 older lessons" in html  # 8 - 5 recent = 3


def test_gaps_exclude_taught_and_table_stakes(tmp_path):
    html = builder.build(_memory(), _scored(), out_path=tmp_path / "d.html").read_text("utf-8")
    # DuckDB is an unmet multi-source gap → present in the gaps list
    assert "DuckDB" in html
    # Kafka is already taught (in memory) and Python is table-stakes → not gaps.
    gaps = html.split("Gap highlights")[1].split("Lesson archive")[0]
    assert "Kafka consumer groups" not in gaps
    assert "Python" not in gaps


def test_empty_memory_no_scored_renders(tmp_path):
    html = builder.build({"skills": {}}, None, out_path=tmp_path / "d.html").read_text("utf-8")
    assert "No lessons yet" in html
    assert "No fresh data" in html


def test_build_from_state_reads_committed_files(tmp_path, monkeypatch):
    import storage
    monkeypatch.setattr(storage, "load_memory", lambda: _memory())
    monkeypatch.setattr(
        storage, "load_last_scored",
        lambda: {"today_skill": "DuckDB", "scored": _scored()},
    )
    monkeypatch.setattr(
        storage, "load_trending_history",
        lambda: {"2026-05-30": {"today_skill": "DuckDB", "scored": _scored()}},
    )
    out = builder.build_from_state(out_path=tmp_path / "d.html")
    html = out.read_text(encoding="utf-8")
    assert "DuckDB" in html and "🎧 today" in html
    assert "Kafka consumer groups" in html  # coverage + archive from memory


def test_escapes_html(tmp_path):
    mem = {"skills": {}}
    scored = [{
        "skill": "C++ <templates>", "score": 1.0, "demand_weight": 1.0, "frequency": 2,
        "sources": ["dev.to & more"], "evidence": "x", "table_stakes": False,
    }]
    html = builder.build(mem, scored, out_path=tmp_path / "d.html").read_text("utf-8")
    assert "<templates>" not in html and "&lt;templates&gt;" in html
