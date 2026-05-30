"""Offline tests for the /recap bot. No network: I/O is monkeypatched."""
from recap import bot

CHAT = "999"


def _mem():
    return {"skills": {
        "Kafka consumer groups": {
            "times_taught": 1, "last_taught": "2026-05-22", "summary": "partitioned consumption",
            "lessons": [{"date": "2026-05-22", "difficulty": "beginner",
                         "summary": "partitioned consumption", "brief": "20260522-kafka.md"}],
        },
        "DuckDB": {
            "times_taught": 1, "last_taught": "2026-05-30", "summary": "in-process OLAP",
            "lessons": [{"date": "2026-05-30", "difficulty": "beginner",
                         "summary": "in-process OLAP", "brief": "20260530-duckdb.md"}],
        },
    }}


def _set_chat(monkeypatch):
    monkeypatch.setattr(bot.config, "TELEGRAM_CHAT_ID", CHAT)


def _update(uid, text, chat=CHAT):
    return {"update_id": uid, "message": {"chat": {"id": int(chat)}, "text": text}}


# --- parsing / security ------------------------------------------------------

def test_recap_questions_filters_chat_and_command(monkeypatch):
    _set_chat(monkeypatch)
    updates = [
        _update(1, "/recap what is kafka?"),       # ours, recap
        _update(2, "hello"),                         # ours, not recap
        _update(3, "/recap deep dive", chat="123"),  # foreign chat → ignored
        _update(4, "/RECAP caps ok"),                # case-insensitive
    ]
    qs = bot.recap_questions(updates)
    assert qs == [(1, "what is kafka?"), (4, "caps ok")]


def test_mentions_token_match():
    assert bot._mentions("Kafka consumer groups", "tell me about kafka")
    assert not bot._mentions("DuckDB", "what is rust")


# --- catalog / brief selection ----------------------------------------------

def test_catalog_lists_all_skills():
    cat = bot._catalog(_mem())
    assert "Kafka consumer groups" in cat and "DuckDB" in cat
    assert "in-process OLAP" in cat


def test_select_briefs_prefers_named_skill(monkeypatch):
    loaded = {"20260522-kafka.md": "Kafka brief body", "20260530-duckdb.md": "DuckDB brief body"}
    monkeypatch.setattr(bot, "load_brief", lambda f: loaded.get(f, ""))
    out = bot._select_briefs("explain kafka rebalancing", _mem())
    assert "Kafka brief body" in out
    assert "DuckDB brief body" not in out  # not relevant to the question


def test_select_briefs_falls_back_to_recent(monkeypatch):
    loaded = {"20260522-kafka.md": "Kafka brief body", "20260530-duckdb.md": "DuckDB brief body"}
    monkeypatch.setattr(bot, "load_brief", lambda f: loaded.get(f, ""))
    out = bot._select_briefs("what should I review?", _mem())  # no skill named
    assert "Kafka brief body" in out and "DuckDB brief body" in out


# --- answer ------------------------------------------------------------------

def test_answer_empty_memory_is_graceful():
    msg = bot.answer("anything", {"skills": {}}, chat_fn=lambda *a, **k: "x")
    assert "haven't completed any lessons" in msg


def test_answer_passes_catalog_and_briefs_to_llm(monkeypatch):
    monkeypatch.setattr(bot, "load_brief", lambda f: "FULL BRIEF TEXT")
    captured = {}

    def fake(messages, **k):
        captured["p"] = messages[0]["content"]
        return "Here is your recap."

    out = bot.answer("recap duckdb", _mem(), chat_fn=fake)
    assert out == "Here is your recap."
    assert "DuckDB" in captured["p"] and "FULL BRIEF TEXT" in captured["p"]


# --- poll orchestration ------------------------------------------------------

def test_poll_answers_and_confirms_offset(monkeypatch):
    _set_chat(monkeypatch)
    monkeypatch.setattr(
        bot, "fetch_updates", lambda: [_update(5, "/recap hi"), _update(6, "noise")]
    )
    monkeypatch.setattr(bot, "load_memory", _mem)
    monkeypatch.setattr(bot, "load_brief", lambda f: "body")
    sent, confirmed = [], []
    monkeypatch.setattr(bot, "send_message", lambda t: sent.append(t))
    monkeypatch.setattr(bot, "confirm", lambda off: confirmed.append(off))

    n = bot.poll(chat_fn=lambda *a, **k: "answer")
    assert n == 1
    assert sent == ["answer"]
    assert confirmed == [7]  # max update_id (6) + 1 — clears the whole queue


def test_poll_confirms_even_when_answer_fails(monkeypatch):
    _set_chat(monkeypatch)
    monkeypatch.setattr(bot, "fetch_updates", lambda: [_update(9, "/recap boom")])
    monkeypatch.setattr(bot, "load_memory", _mem)
    sent, confirmed = [], []
    monkeypatch.setattr(bot, "send_message", lambda t: sent.append(t))
    monkeypatch.setattr(bot, "confirm", lambda off: confirmed.append(off))

    def boom(*a, **k):
        raise RuntimeError("LLM down")

    bot.poll(chat_fn=boom)
    assert confirmed == [10]                          # still confirmed
    assert sent and "couldn't answer" in sent[0]      # apologetic fallback sent


def test_poll_no_updates_noop(monkeypatch):
    monkeypatch.setattr(bot, "fetch_updates", lambda: [])
    assert bot.poll() == 0
