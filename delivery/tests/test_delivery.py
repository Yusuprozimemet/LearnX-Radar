"""Offline tests for delivery. Pure helpers only — no network, no SMTP send."""
import json
from urllib.parse import unquote

from delivery import email_sender, followup, telegram_sender


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


# --- followup links ----------------------------------------------------------

_BRIEF = (
    "# DuckDB\n## Core ideas\nDuckDB is an in-process OLAP database that runs "
    "analytical SQL on local files like Parquet without a server.\n"
)


def test_perplexity_url_embeds_brief_text():
    """The follow-up link must seed Perplexity with the brief TEXT, not a URL —
    Perplexity won't reliably fetch an external link, so the text is inlined."""
    url = followup.perplexity_url("DuckDB", _BRIEF)
    q = unquote(url)
    assert url.startswith("https://www.perplexity.ai/search/new?q=")
    assert "answer my follow-up questions" in q
    assert "in-process OLAP database" in q  # brief text is embedded
    assert "raw.githubusercontent.com" not in q  # no link to scrape


def test_quiz_url_is_recall_quiz_on_brief_text():
    url = followup.quiz_url("DuckDB", _BRIEF)
    q = unquote(url)
    assert url.startswith("https://www.perplexity.ai/search/new?q=")
    assert "ONE AT A TIME" in q
    assert "in-process OLAP database" in q  # brief text grounds the quiz
    assert "raw.githubusercontent.com" not in q


def test_condense_trims_long_brief_to_budget(monkeypatch):
    """A long brief is flattened and trimmed so the deep-link URL stays bounded."""
    monkeypatch.setattr(followup.config, "FOLLOWUP_BRIEF_CHARS", 200)
    long_brief = "# T\n" + ("Sentence number filler here. " * 80)
    out = followup._condense(long_brief, 200)
    assert len(out) <= 201  # budget (+1 for a sentence-ending period)
    assert "\n" not in out  # markdown/newlines flattened to single-line prose


# --- telegram reply markup (buttons) -----------------------------------------

def _buttons(markup: dict) -> list[str]:
    rows = json.loads(markup["reply_markup"])["inline_keyboard"]
    return [btn["text"] for row in rows for btn in row]


def test_reply_markup_followup_only_without_prior():
    markup = telegram_sender._reply_markup(
        {"skill": "DuckDB", "brief_md": _BRIEF}
    )
    assert _buttons(markup) == ["🔎 Ask follow-ups on Perplexity"]


def test_reply_markup_adds_quiz_when_prior_exists():
    markup = telegram_sender._reply_markup(
        {"skill": "DuckDB", "brief_md": _BRIEF,
         "quiz_skill": "Kafka", "quiz_brief_md": _BRIEF}
    )
    assert _buttons(markup) == ["🔎 Ask follow-ups on Perplexity", "🧠 Quiz me on this"]


def test_reply_markup_empty_without_brief():
    assert telegram_sender._reply_markup({"title": "x"}) == {}


# --- email buttons -----------------------------------------------------------

def test_email_buttons_followup_only_without_prior():
    html = email_sender._followup_button({"skill": "DuckDB", "brief_md": _BRIEF})
    assert "Ask follow-ups on Perplexity" in html
    assert "Quiz me on this" not in html


def test_email_buttons_add_quiz_when_prior_exists():
    html = email_sender._followup_button(
        {"skill": "DuckDB", "brief_md": _BRIEF,
         "quiz_skill": "Kafka", "quiz_brief_md": _BRIEF}
    )
    assert "Ask follow-ups on Perplexity" in html and "Quiz me on this" in html


def test_email_buttons_empty_without_brief():
    assert email_sender._followup_button({"title": "x"}) == ""


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
