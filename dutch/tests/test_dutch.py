"""Offline tests for the Dutch coach (v5). Mocked LLM; no network, no TTS."""
import json
from datetime import date
from pathlib import Path

import config
from dutch import audio as dutch_audio
from dutch import cloze, wordlist
from dutch import coach as dutch_coach
from dutch import lesson as dutch_lesson

# The real word bank lives in the private state repo, so tests validate the loader
# against a committed fixture rather than depending on production data.
FIXTURE_WORDLIST = Path(__file__).parent / "fixtures" / "wordlist.json"

# --- wordlist ----------------------------------------------------------------

def test_load_wordlist_validates_structure():
    words = wordlist.load(path=FIXTURE_WORDLIST)
    assert len(words) >= 4
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


# --- Delft audio layout (v9 day 30) -------------------------------------------

def _delft_lesson():
    return dutch_lesson.DutchLesson(
        theme="everyday",
        cefr="A2",
        new_words=[{"id": "a", "nl": "de a", "en": "the a"}],
        review_words=[],
        sentences=[{"id": "a", "nl": "Dit is de a.", "en": "This is the a."}],
        dialogue=[{"speaker": "A", "nl": "Hallo.", "en": "Hi."},
                  {"speaker": "B", "nl": "Goedemorgen.", "en": "Good morning."}],
    )


def test_to_lines_delft_blocks_and_repeat_pauses():
    lines = dutch_audio.to_lines(_delft_lesson())
    # Block A: word, sentence (repeat pause), sentence again. Block B: each of the
    # 2 dialogue lines twice. Block C: the dialogue once more, straight through.
    assert len(lines) == 3 + 4 + 2
    word, s1, s2 = lines[0], lines[1], lines[2]
    assert word.pause_after_factor == 0          # sentence follows immediately
    assert s1.pause_after_factor == config.DUTCH_DELFT_PAUSE_FACTOR
    assert s2.pause_after_factor == 0.5          # self-check replay, short pause
    assert s1.text == s2.text == "Dit is de a."
    block_b = lines[3:7]
    assert [ln.text for ln in block_b] == ["Hallo.", "Hallo.",
                                           "Goedemorgen.", "Goedemorgen."]
    assert all(ln.unit_number == 1 for ln in block_b)
    block_c = lines[7:]
    assert [ln.text for ln in block_c] == ["Hallo.", "Goedemorgen."]
    assert all(ln.unit_number == 2 and ln.pause_after_factor == 0 for ln in block_c)


def test_to_lines_word_without_sentence_gets_the_pause():
    lesson = _delft_lesson()
    lesson.sentences = []  # LLM degraded: gloss only
    lines = dutch_audio.to_lines(lesson)
    assert lines[0].text == "de a"
    assert lines[0].pause_after_factor == config.DUTCH_DELFT_PAUSE_FACTOR


def test_to_lines_legacy_when_delft_disabled(monkeypatch):
    monkeypatch.setattr(config, "DUTCH_DELFT_AUDIO", False)
    lines = dutch_audio.to_lines(_delft_lesson())
    assert len(lines) == 4  # word, sentence, 2 dialogue lines — v5 layout
    assert all(ln.pause_after_factor == 0 for ln in lines)


# --- cloze (v9 day 31) ---------------------------------------------------------

def test_cloze_blanks_first_occurrence_and_strips_article():
    section = cloze.render(
        [{"id": "afspraak", "nl": "de afspraak", "en": "the appointment"}],
        [{"id": "afspraak", "nl": "Ik heb morgen een afspraak.", "en": ""}],
        [{"speaker": "A", "nl": "Hallo!", "en": ""}],
    )
    assert "Ik heb morgen een ___ (1)." in section   # bare noun matched, article-free
    assert "afspraak" in section.rsplit("Antwoorden", 1)[1]  # key holds the answer
    assert "Hallo!" not in section  # dialogue without a blank is left out


def test_cloze_blanks_in_dialogue_keeps_whole_conversation():
    section = cloze.render(
        [{"id": "afspraak", "nl": "de afspraak", "en": "the appointment"}],
        [],
        [{"speaker": "A", "nl": "Hoe laat is je afspraak?", "en": ""},
         {"speaker": "B", "nl": "Om tien uur.", "en": ""}],
    )
    assert "A: Hoe laat is je ___ (1)?" in section
    assert "B: Om tien uur." in section  # unblanked line kept — it is the context


def test_cloze_empty_when_no_word_occurs():
    assert cloze.render(
        [{"id": "afspraak", "nl": "de afspraak", "en": "the appointment"}],
        [{"id": "afspraak", "nl": "Geen match hier.", "en": ""}],
        [],
    ) == ""


def test_lesson_markdown_gains_instructions_and_cloze():
    new_words = [
        {"id": "afspraak", "nl": "de afspraak", "en": "the appointment", "theme": "everyday"}
    ]
    payload = {
        "sentences": [
            {"id": "afspraak", "nl": "Ik heb een afspraak.", "en": "I have an appointment."}
        ],
        "dialogue": [{"speaker": "A", "nl": "Tot morgen!", "en": "See you tomorrow!"}],
    }
    lesson = dutch_lesson.build(
        new_words, [], theme="everyday", chat_fn=_fake_chat_factory(payload)
    )
    assert "Zo oefen je" in lesson.markdown          # Delft practice steps
    assert "Invuloefening" in lesson.markdown        # cloze section appended
    assert "___ (1)" in lesson.markdown


# --- trainer JSON (v9 day 32) ---------------------------------------------------

def test_trainer_payload_blocks_translations_and_block_c():
    from dutch import trainer

    lesson = _delft_lesson()
    # Timings as the audio render reports them: block A (unit 0) sentence twice,
    # block B (unit 1) repeats, block C (unit 2) straight through.
    timings = [
        {"speaker": "ALEX", "text": "de a", "unit": 0, "start_ms": 0, "end_ms": 800},
        {"speaker": "MAYA", "text": "Dit is de a.", "unit": 0, "start_ms": 800, "end_ms": 2000},
        {"speaker": "MAYA", "text": "Dit is de a.", "unit": 0, "start_ms": 3800, "end_ms": 5000},
        {"speaker": "ALEX", "text": "Hallo.", "unit": 1, "start_ms": 5600, "end_ms": 6400},
        {"speaker": "ALEX", "text": "Hallo.", "unit": 1, "start_ms": 7600, "end_ms": 8400},
        {"speaker": "ALEX", "text": "Hallo.", "unit": 2, "start_ms": 9000, "end_ms": 9800},
        {"speaker": "MAYA", "text": "Goedemorgen.", "unit": 2, "start_ms": 10250, "end_ms": 11500},
    ]
    payload = trainer.build_payload(lesson, timings, "dutch-20260609.mp3")

    assert payload["audio_url"].endswith("/dutch-20260609.mp3")
    blocks = [s["block"] for s in payload["segments"]]
    assert blocks == ["A", "A", "A", "B", "B", "C", "C"]
    # Translations joined by exact Dutch text (word gloss, sentence, dialogue).
    by_nl = {s["nl"]: s["en"] for s in payload["segments"]}
    assert by_nl["de a"] == "the a"
    assert by_nl["Dit is de a."] == "This is the a."
    assert by_nl["Goedemorgen."] == "Good morning."
    # Block C span = first C start to last C end — the one-chance exercise's range.
    assert payload["block_c"] == {"start_ms": 9000, "end_ms": 11500}
    assert payload["cloze"]["answers"] == ["a"]  # "de a" -> bare form blanked


def test_trainer_payload_no_block_c_when_no_dialogue():
    from dutch import trainer

    lesson = _delft_lesson()
    lesson.dialogue = []
    timings = [
        {"speaker": "ALEX", "text": "de a", "unit": 0, "start_ms": 0, "end_ms": 800},
    ]
    payload = trainer.build_payload(lesson, timings, "dutch-20260609.mp3")
    assert payload["block_c"] is None


def test_cloze_extract_lines_and_answers_align():
    data = cloze.extract(
        [{"id": "afspraak", "nl": "de afspraak", "en": "the appointment"},
         {"id": "beginnen", "nl": "beginnen", "en": "to begin"}],
        [{"id": "afspraak", "nl": "Ik heb een afspraak.", "en": ""}],
        [{"speaker": "A", "nl": "We beginnen om negen uur.", "en": ""}],
    )
    assert data["lines"] == ["Ik heb een ___ (1).", "A: We ___ (2) om negen uur."]
    assert data["answers"] == ["afspraak", "beginnen"]


def test_trainer_payload_block_b_and_luistertoets():
    from dutch import trainer

    lesson = _delft_lesson()
    lesson.review_words = [{"id": "goedemorgen", "nl": "goedemorgen", "en": "good morning"}]
    timings = [
        {"speaker": "MAYA", "text": "Dit is de a.", "unit": 0, "start_ms": 0, "end_ms": 1200},
        {"speaker": "ALEX", "text": "Hallo.", "unit": 1, "start_ms": 2000, "end_ms": 2800},
        {"speaker": "ALEX", "text": "Hallo.", "unit": 1, "start_ms": 4000, "end_ms": 4800},
        {"speaker": "ALEX", "text": "Hallo.", "unit": 2, "start_ms": 5400, "end_ms": 6200},
        {"speaker": "MAYA", "text": "Goedemorgen.", "unit": 2, "start_ms": 6650, "end_ms": 7900},
    ]
    payload = trainer.build_payload(lesson, timings, "dutch-20260609.mp3")
    # Block B's span (sentence -> pause -> sentence again) powers Delft step 3.
    assert payload["block_b"] == {"start_ms": 2000, "end_ms": 4800}
    # Luistertoets: one entry PER dialogue line, review words blanked too;
    # a line without target words still plays — it just has nothing to fill.
    lt = payload["luistertoets"]
    assert [item["answers"] for item in lt] == [[], ["goedemorgen"]]
    assert lt[1]["nl"] == "___ (1)."


def test_trainer_payload_report_words_order_and_forms(monkeypatch):
    from dutch import trainer

    monkeypatch.setattr(config, "DUTCH_RECALL_ENABLED", True)
    monkeypatch.setattr(config, "TELEGRAM_BOT_USERNAME", "LearnXBot")
    lesson = _delft_lesson()
    lesson.review_words = [{"id": "goedemorgen", "nl": "goedemorgen", "en": "good morning"}]
    payload = trainer.build_payload(lesson, [], "dutch-20260609.mp3")

    rep = payload["report"]
    assert rep["bot"] == "LearnXBot"
    # Word ORDER (new then review) is the contract with dutch_memory's
    # lessons[].words — the positional marks in the /start payload rely on it.
    assert [w["id"] for w in rep["words"]] == ["a", "goedemorgen"]
    # Article stripped: the form is what the page's exam answers contain.
    assert rep["words"][0]["form"] == "a"


def test_trainer_payload_report_bot_empty_when_recall_disabled(monkeypatch):
    from dutch import trainer

    monkeypatch.setattr(config, "DUTCH_RECALL_ENABLED", False)
    monkeypatch.setattr(config, "TELEGRAM_BOT_USERNAME", "LearnXBot")
    payload = trainer.build_payload(_delft_lesson(), [], "x.mp3")
    assert payload["report"]["bot"] == ""  # the page then hides the Save button


# --- mistake-driven coach (v10 day 36) ----------------------------------------

_COACH_BANK = [
    {"id": "a", "nl": "de a", "en": "the a", "theme": "everyday"},
    {"id": "b", "nl": "de b", "en": "the b", "theme": "everyday"},
    {"id": "c", "nl": "het c", "en": "the c", "theme": "tech"},
]


def _canned(payload: dict):
    """A chat_fn that ignores the prompt and returns fixed JSON (accepts any kwargs
    the coach passes — temperature, max_tokens)."""
    return lambda *a, **k: json.dumps(payload)


def test_detect_struggling_needs_net_misses_above_min():
    memory = {"words": {
        "a": {"recall_wrong": 3, "recall_right": 1},  # 3>1 and >=2 -> struggling
        "b": {"recall_wrong": 1, "recall_right": 0},  # one slip (<min) -> not
        "c": {},                                       # no recall data -> not
    }}
    out = dutch_coach.detect_struggling(memory, _COACH_BANK, min_misses=2)
    assert [w["id"] for w in out] == ["a"]
    assert out[0]["nl"] == "de a" and out[0]["wrong"] == 3 and out[0]["right"] == 1


def test_detect_struggling_excludes_when_not_net_failing():
    memory = {"words": {"a": {"recall_wrong": 2, "recall_right": 2}}}  # tied, not failing
    assert dutch_coach.detect_struggling(memory, _COACH_BANK, min_misses=2) == []


def test_detect_struggling_ranked_by_miss_rate_then_count():
    memory = {"words": {
        "a": {"recall_wrong": 2, "recall_right": 0},  # rate 1.0
        "b": {"recall_wrong": 5, "recall_right": 4},  # rate ~0.56, more misses
    }}
    out = dutch_coach.detect_struggling(memory, _COACH_BANK, min_misses=2)
    assert [w["id"] for w in out] == ["a", "b"]  # higher miss-rate first


def test_plan_skips_llm_on_cold_start():
    def boom(*a, **k):
        raise AssertionError("coach must not call the LLM with no struggling words")
    assert dutch_coach.plan([], chat_fn=boom) == {"focus_ids": [], "directive": "", "reason": ""}


def test_plan_caps_focus_and_drops_hallucinated_ids():
    struggling = [{"id": i, "nl": f"de {i}", "en": "", "wrong": 2, "right": 0}
                  for i in ("a", "b", "c", "d")]
    payload = {"focus_ids": ["a", "b", "c", "d", "ghost"],
               "directive": "Emphasize de/het gender", "reason": "het taken as de"}
    out = dutch_coach.plan(struggling, max_focus=3, chat_fn=_canned(payload))
    assert out["focus_ids"] == ["a", "b", "c"]   # capped to MAX_FOCUS, ghost dropped
    assert out["directive"] == "Emphasize de/het gender"
    assert out["reason"] == "het taken as de"


def test_plan_drops_directive_when_no_valid_focus():
    struggling = [{"id": "a", "nl": "de a", "en": "", "wrong": 2, "right": 0}]
    payload = {"focus_ids": ["ghost"], "directive": "drill x", "reason": "y"}
    out = dutch_coach.plan(struggling, chat_fn=_canned(payload))
    assert out["focus_ids"] == [] and out["directive"] == ""  # no focus -> no directive


def test_plan_degrades_to_empty_on_llm_failure():
    struggling = [{"id": "a", "nl": "de a", "en": "", "wrong": 2, "right": 0}]

    def boom(*a, **k):
        raise RuntimeError("NIM down")

    assert dutch_coach.plan(struggling, chat_fn=boom) == {
        "focus_ids": [], "directive": "", "reason": ""}


def test_force_review_ids_pulls_a_non_due_word_ahead_of_the_cap():
    today = date(2026, 6, 5)
    memory = {"words": {
        "a": {"introduced": "2026-06-01", "reps": 3, "due": "2026-12-01"},  # NOT due
    }}
    _new, review = wordlist.select_for_today(
        _COACH_BANK, memory, today, theme="everyday",
        new_count=1, review_max=6, force_review_ids=["a"],
    )
    assert "a" in [w["id"] for w in review]  # forced in despite not being due


def test_force_review_ids_ignores_unknown_or_uintroduced():
    today = date(2026, 6, 5)
    _new, review = wordlist.select_for_today(
        _COACH_BANK, {"words": {}}, today, theme="everyday",
        new_count=1, review_max=6, force_review_ids=["a", "ghost"],
    )
    assert review == []  # 'a' never introduced, 'ghost' not in bank -> nothing forced


def test_empty_directive_leaves_lesson_prompt_unchanged():
    captured = {}

    def capture(messages, max_tokens=1400):
        captured.setdefault("prompts", []).append(messages[0]["content"])
        return json.dumps({"sentences": [], "dialogue": []})

    word = [{"id": "a", "nl": "de a", "en": "the a", "theme": "everyday"}]
    dutch_lesson.build(word, [], theme="everyday", chat_fn=capture)              # default ""
    dutch_lesson.build(word, [], theme="everyday", directive="", chat_fn=capture)
    dutch_lesson.build(word, [], theme="everyday",
                       directive="Contrast de/het", chat_fn=capture)
    base, also_empty, with_dir = captured["prompts"]
    assert base == also_empty                       # empty directive -> identical prompt
    assert with_dir != base and "Contrast de/het" in with_dir


def test_append_log_records_focus_and_struggling(tmp_path):
    log = tmp_path / "dutch_coach_log.md"
    struggling = [{"id": "a", "nl": "de a", "en": "", "wrong": 3, "right": 1}]
    plan_result = {"focus_ids": ["a"], "directive": "de/het gender", "reason": "het as de"}
    dutch_coach.append_log(plan_result, struggling, when=date(2026, 6, 20), path=log)
    text = log.read_text(encoding="utf-8")
    assert "2026-06-20" in text and "focus: a" in text
    assert "a(3/1)" in text and "de/het gender" in text


def test_cloze_sentence_blanks_every_occurrence_numbered_per_line():
    items = cloze.sentence_blanks(
        [{"id": "uur", "nl": "het uur", "en": "the hour"}],
        [{"speaker": "A", "nl": "Om tien uur of om elf uur?", "en": ""},
         {"speaker": "B", "nl": "Om tien uur.", "en": ""}],
    )
    # both occurrences blanked, numbering restarts per line
    assert items[0]["nl"] == "Om tien ___ (1) of om elf ___ (2)?"
    assert items[0]["answers"] == ["uur", "uur"]
    assert items[1]["nl"] == "Om tien ___ (1)."
    assert items[1]["answers"] == ["uur"]
