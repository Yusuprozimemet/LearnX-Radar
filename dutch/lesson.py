"""Build the daily Dutch lesson from a FIXED set of curated words.

One LLM call wraps the given words in CEFR-appropriate example sentences and a short
dialogue. The words themselves are never generated — they come from the frozen
wordlist — and any model output that doesn't map back to a given word id is dropped,
so a bad generation degrades to the verified gloss rather than a wrong word.
"""
import logging
from dataclasses import dataclass, field

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
    return lesson


def _summary(theme: str, new_words: list[dict]) -> str:
    glosses = ", ".join((w.get("en") or w["nl"]).removeprefix("the ") for w in new_words[:4])
    return f"Dutch ({theme}): {glosses}" if glosses else f"Dutch ({theme})"


def _render_markdown(lesson: DutchLesson) -> str:
    by_id = {s["id"]: s for s in lesson.sentences}
    out: list[str] = [f"## 🇳🇱 Dutch ({lesson.cefr}) — {lesson.theme}", ""]

    out.append("**Nieuwe woorden (new words)**")
    for w in lesson.new_words:
        line = f"- **{w['nl']}** — {w.get('en', '')}"
        s = by_id.get(w["id"])
        if s:
            line += f"  \n  _{s['nl']}_" + (f" — {s['en']}" if s.get("en") else "")
        out.append(line)
    out.append("")

    if lesson.review_words:
        out.append("**Herhaling (review)**")
        for w in lesson.review_words:
            out.append(f"- {w['nl']} — {w.get('en', '')}")
        out.append("")

    if lesson.dialogue:
        out.append("**Gesprek (dialogue)**")
        for d in lesson.dialogue:
            line = f"- {d['speaker']}: {d['nl']}"
            if d.get("en"):
                line += f" — _{d['en']}_"
            out.append(line)
        out.append("")

    return "\n".join(out).strip()
