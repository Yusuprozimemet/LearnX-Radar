"""Build the daily Dutch lesson from a FIXED set of curated words.

One LLM call wraps the given words in CEFR-appropriate example sentences and a short
dialogue. The words themselves are never generated — they come from the frozen
wordlist — and any model output that doesn't map back to a given word id is dropped,
so a bad generation degrades to the verified gloss rather than a wrong word.
"""
import logging
from dataclasses import dataclass, field

import config
from dutch import cloze
from dutch.prompt_loader import load_prompt
from learnx.llm import chat, parse_json_response

log = logging.getLogger(__name__)


@dataclass
class DutchLesson:
    theme: str
    cefr: str
    new_words: list[dict]
    review_words: list[dict]
    sentences: list[dict] = field(default_factory=list)  # {"id","nl","en"}
    dialogue: list[dict] = field(default_factory=list)    # {"speaker","nl","en"}
    markdown: str = ""
    summary: str = ""


def _topic_line(theme: str, topic: str | None) -> str:
    if theme == "tech" and topic:
        return f"Center the dialogue on this real-world tech topic, in simple Dutch: {topic}."
    return "Keep the dialogue about everyday life (work, shopping, appointments, travel)."


def _format_words(words: list[dict]) -> str:
    return "\n".join(f"- {w['id']} — {w['nl']} — {w.get('en', '')}" for w in words)


def build(
    new_words: list[dict],
    review_words: list[dict] | None = None,
    *,
    theme: str,
    topic: str | None = None,
    cefr: str = "A2",
    chat_fn=chat,
) -> DutchLesson:
    """Return a DutchLesson for the given words. The LLM only writes sentences and a
    dialogue around these exact words; vocabulary is never invented."""
    review_words = review_words or []
    all_words = new_words + review_words
    lesson = DutchLesson(
        theme=theme, cefr=cefr, new_words=new_words, review_words=review_words
    )
    if not all_words:
        return lesson

    valid_ids = {w["id"] for w in all_words}
    prompt = load_prompt("lesson.txt").format(
        cefr=cefr,
        theme=theme,
        topic_line=_topic_line(theme, topic),
        words=_format_words(all_words),
    )
    try:
        raw = chat_fn([{"role": "user", "content": prompt}], max_tokens=1400)
        data = parse_json_response(raw)
    except Exception as exc:  # degrade: keep the verified words, drop the generation
        log.warning("Dutch lesson generation failed (%s); using glosses only", exc)
        data = {}

    if isinstance(data, dict):
        for s in data.get("sentences", []):
            if isinstance(s, dict) and s.get("id") in valid_ids and s.get("nl"):
                lesson.sentences.append(
                    {"id": s["id"], "nl": s["nl"].strip(), "en": (s.get("en") or "").strip()}
                )
        for d in data.get("dialogue", []):
            speaker = str(d.get("speaker", "")).strip().upper() if isinstance(d, dict) else ""
            if speaker in ("A", "B") and isinstance(d, dict) and d.get("nl"):
                lesson.dialogue.append(
                    {"speaker": speaker, "nl": d["nl"].strip(), "en": (d.get("en") or "").strip()}
                )

    lesson.summary = _summary(theme, new_words)
    lesson.markdown = _render_markdown(lesson)
    # Delft Phase 2 (v9 day 31): deterministic cloze over today's new words. Empty
    # when no new word occurs in the text — the section then simply doesn't render.
    if config.DUTCH_CLOZE_ENABLED:
        section = cloze.render(lesson.new_words, lesson.sentences, lesson.dialogue)
        if section:
            lesson.markdown += "\n\n" + section
    # Trainer link (v9 day 32) — flows into the PDF and email; Telegram also gets
    # an inline button. The page checks answers and enforces the one-chance listen.
    if config.DUTCH_TRAINER_ENABLED and lesson.markdown:
        lesson.markdown += (
            f"\n\n🎧 _Oefen interactief (train interactively):_ {config.TRAINER_URL}"
        )
    return lesson


def _summary(theme: str, new_words: list[dict]) -> str:
    glosses = ", ".join((w.get("en") or w["nl"]).removeprefix("the ") for w in new_words[:4])
    return f"Dutch ({theme}): {glosses}" if glosses else f"Dutch ({theme})"


def _render_markdown(lesson: DutchLesson) -> str:
    """Render the lesson as markdown. Convention: **Dutch is bold**, _English is
    italic_ — both the email (markdown->HTML) and Telegram (markdown->Telegram HTML)
    renderers map these to <b>/<i>, so Dutch and English read distinctly."""
    by_id = {s["id"]: s for s in lesson.sentences}
    out: list[str] = [f"## 🇳🇱 Dutch ({lesson.cefr}) — {lesson.theme}", ""]

    # Delft practice steps (v9 day 30): map the audio's blocks to the method's four
    # input steps, so the MP3 is used as an imitation exercise, not background audio.
    if config.DUTCH_DELFT_AUDIO:
        out += [
            "**Zo oefen je (how to practice — Delft method)**",
            "1. _Blok A & B:_ luister, **spreek na in de pauze**, luister opnieuw "
            "— _listen, repeat aloud in the pause, listen again_",
            "2. _Blok C:_ luister naar het hele gesprek **met** de tekst "
            "— _whole dialogue, with the transcript_",
            "3. Herhaal Blok A & B **zonder** tekst — _replay without the transcript_",
            "4. Luister Blok C nog één keer zonder tekst — _final listen, no transcript_",
            "",
        ]

    out.append("**Nieuwe woorden (new words)**")
    for w in lesson.new_words:
        en = w.get("en", "")
        line = f"- **{w['nl']}**" + (f" — _{en}_" if en else "")
        s = by_id.get(w["id"])
        if s:
            line += f"  \n  **{s['nl']}**" + (f" — _{s['en']}_" if s.get("en") else "")
        out.append(line)
    out.append("")

    if lesson.review_words:
        out.append("**Herhaling (review)**")
        for w in lesson.review_words:
            en = w.get("en", "")
            out.append(f"- **{w['nl']}**" + (f" — _{en}_" if en else ""))
        out.append("")

    if lesson.dialogue:
        out.append("**Gesprek (dialogue)**")
        for d in lesson.dialogue:
            line = f"- {d['speaker']}: **{d['nl']}**"
            if d.get("en"):
                line += f" — _{d['en']}_"
            out.append(line)
        out.append("")

    return "\n".join(out).strip()
