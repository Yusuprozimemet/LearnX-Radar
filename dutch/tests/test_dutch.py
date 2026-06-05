"""Offline tests for the Dutch coach (v5). Mocked LLM; no network, no TTS."""
import json
from datetime import date

from dutch import audio as dutch_audio
from dutch import lesson as dutch_lesson
from dutch import wordlist

# --- wordlist ----------------------------------------------------------------

def test_load_real_wordlist_is_valid():
    words = wordlist.load()
    assert len(words) > 50
    ids = [w["id"] for w in words]
    assert len(ids) == len(set(ids))  # unique ids
    assert all(w.get("nl") and w.get("theme") in wordlist.THEMES for w in words)


def test_theme_alternates_day_to_day():
    d0 = date(2026, 6, 4)  # ordinal even -> tech
    d1 = date(2026, 6, 5)  # ordinal odd  -> everyday
    assert wordlist.theme_for(d0) != wordlist.theme_for(d1)


_BANK = [
    {"id": "a", "nl": "de a", "en": "the a", "theme": "everyday"},
    {"id": "b", "nl": "de b", "en": "the b", "theme": "everyday"},
    {"id": "c", "nl": "het c", "en": "the c", "theme": "tech"},
]


def test_select_excludes_introduced_and_returns_due_reviews():
    today = date(2026, 6, 5)
    memory = {
        "words": {
            "a": {"introduced": "2026-06-01", "reps": 1, "due": "2026-06-04"},  # overdue
        }
    }
    new_w, review_w = wordlist.select_for_today(
        _BANK, memory, today, theme="everyday", new_count=2, review_max=6
    )
    new_ids = [w["id"] for w in new_w]
    review_ids = [w["id"] for w in review_w]
    assert "a" not in new_ids            # already introduced -> not new
    assert review_ids == ["a"]           # due today -> surfaces for review
    assert "b" in new_ids                # fresh everyday word chosen as new


def test_select_falls_back_when_theme_exhausted():
    today = date(2026, 6, 5)
    new_w, _ = wordlist.select_for_today(
        _BANK, {"words": {}}, today, theme="tech", new_count=3, review_max=0
    )
    # only one tech word exists; selection tops up from other fresh words
    assert len(new_w) == 3


# --- lesson builder ----------------------------------------------------------

def _fake_chat_factory(payload: dict):
    def fake_chat(messages, max_tokens=1400):
        return json.dumps(payload)
    return fake_chat


def test_build_keeps_only_given_word_ids():
    new_words = [
        {"id": "afspraak", "nl": "de afspraak", "en": "the appointment", "theme": "everyday"}
    ]
    payload = {
        "sentences": [
            {"id": "afspraak", "nl": "Ik heb een afspraak.", "en": "I have an appointment."},
            {"id": "ghost", "nl": "Verzonnen.", "en": "Made up."},  # not a given word
        ],
        "dialogue": [
            {"speaker": "A", "nl": "Hallo!", "en": "Hello!"},
            {"speaker": "C", "nl": "Foute spreker.", "en": "Bad speaker."},  # invalid speaker
        ],
    }
    lesson = dutch_lesson.build(
        new_words, [], theme="everyday", chat_fn=_fake_chat_factory(payload)
    )
    assert [s["id"] for s in lesson.sentences] == ["afspraak"]   # ghost dropped
    assert [d["speaker"] for d in lesson.dialogue] == ["A"]      # bad speaker dropped
    assert "de afspraak" in lesson.markdown
    assert "Ik heb een afspraak." in lesson.markdown


def test_build_degrades_to_gloss_on_llm_failure():
    new_words = [
        {"id": "afspraak", "nl": "de afspraak", "en": "the appointment", "theme": "everyday"}
    ]

    def boom(messages, max_tokens=1400):
        raise RuntimeError("LLM down")

    lesson = dutch_lesson.build(new_words, [], theme="everyday", chat_fn=boom)
    assert lesson.sentences == []                 # no generated sentences
    assert "de afspraak" in lesson.markdown       # verified word still shown
    assert "the appointment" in lesson.markdown


def test_build_empty_when_no_words():
    lesson = dutch_lesson.build([], [], theme="everyday", chat_fn=_fake_chat_factory({}))
    assert lesson.markdown == ""
    assert lesson.sentences == []


def test_tech_topic_injected_into_prompt():
    captured = {}

    def capture(messages, max_tokens=1400):
        captured["prompt"] = messages[0]["content"]
        return json.dumps({"sentences": [], "dialogue": []})

    dutch_lesson.build(
        [{"id": "bestand", "nl": "het bestand", "en": "the file", "theme": "tech"}],
        [],
        theme="tech",
        topic="WebAssembly",
        chat_fn=capture,
    )
    assert "WebAssembly" in captured["prompt"]
    assert "het bestand" in captured["prompt"]  # the fixed word is handed to the LLM


# --- audio line assembly -----------------------------------------------------

def test_to_lines_reads_words_then_dialogue_with_speaker_map():
    lesson = dutch_lesson.DutchLesson(
        theme="everyday",
        cefr="A2",
        new_words=[{"id": "a", "nl": "de a", "en": "the a"}],
        review_words=[],
        sentences=[{"id": "a", "nl": "Dit is de a.", "en": "This is the a."}],
        dialogue=[{"speaker": "A", "nl": "Hallo.", "en": "Hi."},
                  {"speaker": "B", "nl": "Goedemorgen.", "en": "Good morning."}],
    )
    lines = dutch_audio.to_lines(lesson)
    texts = [ln.text for ln in lines]
    assert "de a" in texts and "Dit is de a." in texts
    # speaker A -> ALEX, B -> MAYA (the audio_builder voice-map keys)
    speakers = {ln.text: ln.speaker for ln in lines}
    assert speakers["Hallo."] == "ALEX"
    assert speakers["Goedemorgen."] == "MAYA"
