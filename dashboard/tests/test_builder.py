"""Offline tests for the dashboard renderer. Pure HTML, no network."""
import config
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
    # archive now embeds a player streaming the MP3 from its Release asset
    assert f"{config.RELEASES_AUDIO_BASE}/lesson-20260529.mp3" in html


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


def test_archive_player_uses_release_url(tmp_path):
    html = builder.build(_memory(), [], out_path=tmp_path / "d.html").read_text("utf-8")
    assert "<audio" in html
    assert f"src='{config.RELEASES_AUDIO_BASE}/lesson-20260529.mp3'" in html


def test_archive_no_audio_falls_back_to_delivery_note(tmp_path):
    mem = {"skills": {"X": {"times_taught": 1, "last_taught": "2026-05-10",
                            "lessons": [{"date": "2026-05-10", "title": "X",
                                         "difficulty": "beginner", "summary": "s",
                                         "audio": ""}]}}}
    html = builder.build(mem, [], out_path=tmp_path / "d.html").read_text("utf-8")
    assert "<audio" not in html
    assert "delivered via Telegram" in html


def test_header_has_feed_and_releases_links(tmp_path):
    html = builder.build({"skills": {}}, [], out_path=tmp_path / "d.html").read_text("utf-8")
    assert config.FEED_URL in html
    assert config.RELEASES_PAGE_URL in html


def test_escapes_html(tmp_path):
    mem = {"skills": {}}
    scored = [{
        "skill": "C++ <templates>", "score": 1.0, "demand_weight": 1.0, "frequency": 2,
        "sources": ["dev.to & more"], "evidence": "x", "table_stakes": False,
    }]
    html = builder.build(mem, scored, out_path=tmp_path / "d.html").read_text("utf-8")
    assert "<templates>" not in html and "&lt;templates&gt;" in html


# --- Dutch tab (v5) ----------------------------------------------------------

def _dutch_memory():
    return {
        "version": 1,
        "cefr": "A2",
        "streak": 3,
        "words": {
            "afspraak": {"introduced": "2026-06-04", "reps": 1, "due": "2000-01-01"},  # overdue
            "bestand": {"introduced": "2026-06-05", "reps": 2, "due": "2999-01-01"},
        },
        "lessons": [
            {"date": "2026-06-05", "theme": "tech", "audio": "dutch-20260605.mp3",
             "words": ["bestand"], "summary": "files"},
        ],
    }


def test_tabs_render_with_radar_default(tmp_path):
    html = builder.build(
        _memory(), _scored(), today_skill="DuckDB", out_path=tmp_path / "d.html",
        dutch=_dutch_memory(),
    ).read_text("utf-8")
    # both tabs present, radar visible, dutch hidden by default
    assert "data-tab='radar'" in html and "data-tab='dutch'" in html
    assert "id='tab-radar'" in html
    assert "id='tab-dutch' style='display:none'" in html


def test_dutch_tab_shows_progress_words_and_archive(tmp_path):
    html = builder.build(
        _memory(), _scored(), out_path=tmp_path / "d.html", dutch=_dutch_memory()
    ).read_text("utf-8")
    assert "Dutch progress" in html
    assert "Words learned" in html and "Streak" in html
    # one of the two words is overdue → "Due for review today" count is at least 1
    assert "Due for review today" in html
    # recent-words table joins the SR memory with the committed bank for nl/en text
    assert "de afspraak" in html and "the appointment" in html
    # Dutch lesson archive streams its MP3 from the Release asset
    assert f"{config.RELEASES_AUDIO_BASE}/dutch-20260605.mp3" in html


def test_dutch_tab_empty_state(tmp_path):
    html = builder.build(
        _memory(), _scored(), out_path=tmp_path / "d.html", dutch={}
    ).read_text("utf-8")
    assert "No Dutch lessons yet" in html  # empty Dutch memory → friendly empty state


def test_build_without_dutch_still_renders_radar(tmp_path):
    # old callers that pass no dutch arg must still work (back-compat)
    html = builder.build(_memory(), _scored(), out_path=tmp_path / "d.html").read_text("utf-8")
    assert "Trending today" in html and "No Dutch lessons yet" in html
