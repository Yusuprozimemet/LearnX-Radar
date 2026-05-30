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
    for heading in ("Trending this week", "Your coverage", "Gap highlights", "Lesson archive"):
        assert heading in html
    assert "DuckDB" in html and "🎧 today" in html        # today's pick marked
    assert "Kafka consumer groups" in html                # archive lists the lesson
    assert "<audio" not in html                            # metadata-only: no players


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


def test_escapes_html(tmp_path):
    mem = {"skills": {}}
    scored = [{
        "skill": "C++ <templates>", "score": 1.0, "demand_weight": 1.0, "frequency": 2,
        "sources": ["dev.to & more"], "evidence": "x", "table_stakes": False,
    }]
    html = builder.build(mem, scored, out_path=tmp_path / "d.html").read_text("utf-8")
    assert "<templates>" not in html and "&lt;templates&gt;" in html
