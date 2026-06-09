"""Offline tests for delivery. Pure helpers only — no network, no SMTP send."""
import json
from urllib.parse import unquote

from delivery import devto_publisher, email_sender, followup, telegram_sender


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


# --- Dutch delivery (v5) -----------------------------------------------------

_DUTCH_WORDS = [{"id": "afspraak", "nl": "de afspraak", "en": "the appointment"}]
_DUTCH_MD = "## 🇳🇱 Dutch (A2) — everyday\n\n**Nieuwe woorden**\n- **de afspraak** — the appointment"


def test_dutch_quiz_url_embeds_words():
    url = followup.dutch_quiz_url(_DUTCH_WORDS)
    q = unquote(url)
    assert url.startswith("https://www.perplexity.ai/search/new?q=")
    assert "de afspraak" in q and "the appointment" in q
    assert "ONE question at a time" in q


def test_email_dutch_section_present_only_when_set():
    assert email_sender._dutch_html({"title": "x"}) == ""  # no dutch -> nothing
    html = email_sender._dutch_html(
        {"dutch": {"markdown": _DUTCH_MD, "quiz_words": _DUTCH_WORDS}}
    )
    assert "de afspraak" in html
    assert "Quiz me in Dutch" in html  # quiz button rendered when words present


def test_email_dutch_section_no_button_without_quiz_words():
    html = email_sender._dutch_html({"dutch": {"markdown": _DUTCH_MD}})
    assert "de afspraak" in html
    assert "Quiz me in Dutch" not in html


def test_email_attaches_second_dutch_mp3(tmp_path, monkeypatch):
    monkeypatch.setattr(email_sender.config, "EMAIL_FROM", "a@x.com")
    monkeypatch.setattr(email_sender.config, "EMAIL_TO", "b@x.com")
    lesson = _lesson(tmp_path)
    dmp3 = tmp_path / "dutch-20260605.mp3"
    dmp3.write_bytes(b"ID3dutch")
    lesson["dutch"] = {"markdown": _DUTCH_MD, "mp3_path": str(dmp3)}
    msg = email_sender._build_message(lesson)
    names = sorted(
        p.get_filename() for p in msg.get_payload() if p.get_content_maintype() == "audio"
    )
    assert names == ["dutch-20260605.mp3", "lesson-20260530.mp3"]


def test_telegram_dutch_markup_and_html():
    markup = telegram_sender._dutch_reply_markup({"quiz_words": _DUTCH_WORDS})
    # Delft trainer button (v9) leads; the recall-quiz button follows when words exist.
    assert _buttons(markup) == ["🎧 Train this lesson (Delft)", "🇳🇱 Quiz me in Dutch"]
    assert _buttons(telegram_sender._dutch_reply_markup({})) == [
        "🎧 Train this lesson (Delft)"
    ]
    out = telegram_sender._dutch_html(_DUTCH_MD, 1024)
    assert "<b>de afspraak</b>" in out          # Dutch word rendered bold
    assert "**" not in out and "##" not in out  # raw markdown markers gone
    assert "<b>Nieuwe woorden</b>" in out       # heading/label bolded


def test_telegram_dutch_markup_empty_when_trainer_off(monkeypatch):
    monkeypatch.setattr(telegram_sender.config, "DUTCH_TRAINER_ENABLED", False)
    assert telegram_sender._dutch_reply_markup({}) == {}  # no words, no trainer -> {}


def test_telegram_dutch_html_italicises_english_and_keeps_tags_intact():
    md = (
        "**Nieuwe woorden**\n"
        "- **de afspraak** — _the appointment_\n"
        "  **Ik heb een afspraak.** — _I have one._"
    )
    out = telegram_sender._dutch_html(md, 1024)
    assert "<i>the appointment</i>" in out      # English italicised
    assert "<b>Ik heb een afspraak.</b>" in out  # Dutch sentence bold
    # trimming happens at a line boundary, so tags are never split
    short = telegram_sender._dutch_html(md, 150)
    assert "<b>de afspraak</b>" in short          # kept the early lines
    assert "Ik heb een afspraak" not in short      # dropped the later line (trimmed)
    assert short.count("<b>") == short.count("</b>")  # tags balanced (no mid-tag cut)
    assert short.count("<i>") == short.count("</i>")


# --- run report --------------------------------------------------------------

class _OkResp:
    ok = True


def test_send_report_dms_owner_and_trims(monkeypatch):
    monkeypatch.setattr(telegram_sender.config, "TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setattr(telegram_sender.config, "TELEGRAM_CHAT_ID", "owner")
    captured = {}

    def fake_post(url, data=None, timeout=None, **kw):
        captured["url"] = url
        captured["data"] = data
        return _OkResp()

    monkeypatch.setattr(telegram_sender.requests, "post", fake_post)
    telegram_sender.send_report("x" * 5000)
    assert "tok" in captured["url"]
    assert captured["data"]["chat_id"] == "owner"
    assert len(captured["data"]["text"]) == telegram_sender.MESSAGE_LIMIT


def test_send_report_noop_without_config(monkeypatch):
    monkeypatch.setattr(telegram_sender.config, "TELEGRAM_BOT_TOKEN", None)
    monkeypatch.setattr(telegram_sender.config, "TELEGRAM_CHAT_ID", None)

    def boom(*a, **k):
        raise AssertionError("must not POST without bot token + chat id")

    monkeypatch.setattr(telegram_sender.requests, "post", boom)
    telegram_sender.send_report("failures")


def test_send_tries_all_targets_then_raises_on_failure(monkeypatch):
    monkeypatch.setattr(telegram_sender, "_render_pdfs", lambda lesson: (None, None))
    monkeypatch.setattr(telegram_sender, "_targets", lambda: ["bad", "good"])
    delivered = []

    def fake_deliver(chat_id, lesson, brief_pdf, dutch_pdf):
        delivered.append(chat_id)
        if chat_id == "bad":
            raise RuntimeError("PEER_ID_INVALID")

    monkeypatch.setattr(telegram_sender, "_deliver_one", fake_deliver)
    try:
        telegram_sender.send({"title": "t", "mp3_path": "x.mp3"})
        raise AssertionError("send must re-raise after a failed target")
    except RuntimeError as exc:
        assert "bad" in str(exc)
    assert delivered == ["bad", "good"]  # the failure didn't block the other target


# --- dev.to cross-post -------------------------------------------------------

class _FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"url": "https://dev.to/x/draft-temp-slug"}


def test_devto_strip_h1():
    assert devto_publisher._strip_h1("# DuckDB\n\nbody") == "body"
    assert devto_publisher._strip_h1("no heading\nmore") == "no heading\nmore"


def test_devto_publish_creates_draft(monkeypatch):
    monkeypatch.setattr(devto_publisher.config, "DEVTO_PUBLISH_ENABLED", True)
    monkeypatch.setattr(devto_publisher.config, "DEVTO_API_KEY", "k")
    monkeypatch.setattr(devto_publisher.config, "DEVTO_PUBLISHED", False)
    monkeypatch.setattr(devto_publisher.config, "DEVTO_POST_TAGS", ["programming"])
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResp()

    monkeypatch.setattr(devto_publisher.requests, "post", fake_post)
    lesson = {"title": "DuckDB", "skill": "DuckDB", "brief_md": "# DuckDB\n\nfast OLAP"}
    assert devto_publisher.publish(lesson, force=True) is True
    art = captured["json"]["article"]
    assert art["title"] == "DuckDB"
    assert art["published"] is False                 # draft
    assert "# DuckDB" not in art["body_markdown"]    # leading H1 stripped
    assert "t.me/learnradar" in art["body_markdown"] # CTA footer appended
    assert captured["headers"]["api-key"] == "k"


def test_devto_skips_without_key(monkeypatch):
    monkeypatch.setattr(devto_publisher.config, "DEVTO_PUBLISH_ENABLED", True)
    monkeypatch.setattr(devto_publisher.config, "DEVTO_API_KEY", "")

    def boom(*a, **k):
        raise AssertionError("must not POST without a key")

    monkeypatch.setattr(devto_publisher.requests, "post", boom)
    assert devto_publisher.publish({"brief_md": "x"}, force=True) is False


def test_devto_skips_on_wrong_weekday(monkeypatch):
    monkeypatch.setattr(devto_publisher.config, "DEVTO_PUBLISH_ENABLED", True)
    monkeypatch.setattr(devto_publisher.config, "DEVTO_API_KEY", "k")
    # Force the gate: configured weekday is "today + 1", so a non-forced call skips.
    from datetime import date
    monkeypatch.setattr(devto_publisher.config, "DEVTO_POST_WEEKDAY",
                        (date.today().weekday() + 1) % 7)

    def boom(*a, **k):
        raise AssertionError("must not POST on the wrong weekday")

    monkeypatch.setattr(devto_publisher.requests, "post", boom)
    assert devto_publisher.publish({"brief_md": "x"}) is False
