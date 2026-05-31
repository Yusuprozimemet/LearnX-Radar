"""Tests for PII redaction at ingestion (radar/privacy.py)."""
from radar import privacy


def test_scrubs_email():
    assert privacy.scrub("Apply to jane.doe@acme.io today") == "Apply to [email] today"


def test_scrubs_phone():
    assert "[phone]" in privacy.scrub("Call us at +1 (555) 123-4567 to apply")


def test_scrubs_handle():
    assert privacy.scrub("DM @recruiter_jane on Telegram") == "DM [handle] on Telegram"


def test_keeps_technical_text():
    text = "We use DuckDB, Rust async/await, and Kubernetes 1.30 in production"
    assert privacy.scrub(text) == text


def test_does_not_eat_version_numbers():
    assert privacy.scrub("Python 3.12 and Node 20.11") == "Python 3.12 and Node 20.11"


def test_empty_is_safe():
    assert privacy.scrub("") == ""
