"""Offline tests for delivery. Pure helpers only — no network, no SMTP send."""
from delivery import email_sender, telegram_sender


def _lesson(
    tmp_path,
    summary="DuckDB is a fast in-process OLAP database.",
    brief="# DuckDB\n\nA database.",
):
    mp3 = tmp_path / "lesson-20260530.mp3"
    mp3.write_bytes(b"ID3fakecontent")  # MIMEAudio just needs bytes
    return {
        "title": "DuckDB",
        "skill": "DuckDB",
        "summary": summary,
        "difficulty": "beginner",
        "mp3_path": str(mp3),
        "brief_md": brief,
    }


# --- telegram caption --------------------------------------------------------

def test_caption_has_title_summary_footer():
    cap = telegram_sender._caption(
        {"title": "DuckDB", "summary": "fast OLAP", "difficulty": "beginner"}
    )
    assert "DuckDB" in cap and "fast OLAP" in cap and "LearnX-Radar" in cap


def test_caption_capped_at_limit():
    cap = telegram_sender._caption(
        {"title": "DuckDB", "summary": "x" * 5000, "difficulty": "beginner"}
    )
    assert len(cap) <= telegram_sender.CAPTION_LIMIT
    assert "DuckDB" in cap and "LearnX-Radar" in cap  # title + footer survive
    assert "…" in cap  # summary was trimmed


# --- email markdown -> html --------------------------------------------------

def test_markdown_renders_structures():
    md = (
        "# Title\n## Sub\n\nA paragraph with **bold** and `code`.\n\n"
        "- one\n- two\n\n```python\nx = 1\n```"
    )
    out = email_sender._markdown_to_html(md)
    assert "<h1>Title</h1>" in out
    assert "<h2>Sub</h2>" in out
    assert "<strong>bold</strong>" in out and "<code>code</code>" in out
    assert "<ul>" in out and out.count("<li>") == 2
    assert "<pre" in out and "x = 1" in out


def test_markdown_escapes_html():
    out = email_sender._markdown_to_html("A <script> & stuff")
    assert "<script>" not in out and "&lt;script&gt;" in out


# --- email message assembly --------------------------------------------------

def test_build_message_has_subject_and_audio_attachment(tmp_path, monkeypatch):
    monkeypatch.setattr(email_sender.config, "EMAIL_FROM", "a@x.com")
    monkeypatch.setattr(email_sender.config, "EMAIL_TO", "b@x.com")
    msg = email_sender._build_message(_lesson(tmp_path))

    assert "DuckDB" in msg["Subject"]
    assert msg["To"] == "b@x.com"
    parts = msg.get_payload()
    assert any(p.get_content_type() == "text/html" for p in parts)
    audio = [p for p in parts if p.get_content_maintype() == "audio"]
    assert audio and audio[0].get_filename() == "lesson-20260530.mp3"
