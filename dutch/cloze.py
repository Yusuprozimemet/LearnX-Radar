"""Fill-in-the-blanks (cloze) exercise — Delft Phase 2: production (v9 day 31).

Deterministic, no LLM: today's NEW words are blanked out of the example sentences
and dialogue. Same correct-by-design stance as the wordlist — nothing is generated,
so nothing can be wrong. Matching is exact-form, word-boundary, case-insensitive;
an inflected form the bank doesn't carry is simply not blanked (a missed blank
degrades to a normal sentence, never a wrong blank).
"""
import re


def match_form(nl: str) -> str:
    """The form searched for in the text: the bank stores nouns with their article
    ("de afspraak"), but in a sentence the noun appears with any (or no) article.
    Public because the trainer payload (v9 day 33) uses the same form to map the
    page's per-blank results back to word ids."""
    return re.sub(r"^(de|het)\s+", "", nl.strip(), flags=re.IGNORECASE)


def extract(new_words: list[dict], sentences: list[dict], dialogue: list[dict]) -> dict:
    """Structured cloze: {"lines": [str, ...], "answers": [str, ...]}.

    Each new word is blanked (as `___ (n)`) at its FIRST occurrence across the
    example sentences then the dialogue. Example sentences are included only when
    they got a blank (the rest are context-free one-liners — noise); the dialogue
    is all-or-nothing — the conversation is the context. `answers[n-1]` is blank n.
    Empty answers -> no exercise. Shared by render() (PDF/Telegram markdown) and
    the trainer JSON (v9 day 32).
    """
    remaining: dict[str, re.Pattern] = {}
    for w in new_words:
        form = match_form(w.get("nl", ""))
        if form:
            remaining[form] = re.compile(rf"\b{re.escape(form)}\b", re.IGNORECASE)

    answers: list[str] = []
    lines: list[str] = []

    def blank(text: str) -> tuple[str, bool]:
        """Blank the first unblanked new word found in `text`."""
        hit = False
        for form, pattern in list(remaining.items()):
            new_text, n = pattern.subn(f"___ ({len(answers) + 1})", text, count=1)
            if n:
                answers.append(form)
                del remaining[form]
                text, hit = new_text, True
        return text, hit

    for s in sentences:
        text, hit = blank(s.get("nl", ""))
        if hit:
            lines.append(text)
    dialogue_lines: list[str] = []
    dialogue_hit = False
    for d in dialogue:
        text, hit = blank(d.get("nl", ""))
        dialogue_hit = dialogue_hit or hit
        dialogue_lines.append(f"{d.get('speaker', '')}: {text}")
    if dialogue_hit:
        lines.extend(dialogue_lines)

    return {"lines": lines, "answers": answers}


def sentence_blanks(words: list[dict], dialogue: list[dict]) -> list[dict]:
    """Per-dialogue-line cloze for the trainer's luistertoets (v9 day 32): hear the
    sentence once, then produce its target words.

    Unlike extract() (one blank per word across the whole text — the printable
    gatentekst), every occurrence of any target word is blanked per line, and
    numbering restarts per line, because each sentence is checked on its own right
    after its one listen. `words` is typically new + review (more blanks = more
    production). Lines without a hit keep empty answers — they still play, there is
    just nothing to fill.
    """
    patterns = []
    for w in words:
        form = match_form(w.get("nl", ""))
        if form:
            patterns.append((form, re.compile(rf"\b{re.escape(form)}\b", re.IGNORECASE)))

    out: list[dict] = []
    for d in dialogue:
        text = d.get("nl", "")
        answers: list[str] = []
        for form, pattern in patterns:
            while True:
                new_text, n = pattern.subn(f"___ ({len(answers) + 1})", text, count=1)
                if not n:
                    break
                answers.append(form)
                text = new_text
        out.append({"speaker": d.get("speaker", ""), "nl": text, "answers": answers,
                    "en": d.get("en", "")})
    return out


def render(new_words: list[dict], sentences: list[dict], dialogue: list[dict]) -> str:
    """Markdown cloze section, or "" when no new word occurs in the text (the
    section then simply doesn't render — same degrade as other optional parts)."""
    data = extract(new_words, sentences, dialogue)
    if not data["answers"]:
        return ""
    out = [
        "**Invuloefening (fill in the blanks)** — _Delft fase 2_",
        "1. Vul eerst in uit je geheugen _(fill from memory first)_.",
        "2. Te moeilijk? Luister Blok C nog ÉÉN keer en vul de rest in "
        "_(replay Block C once — one chance — and fill the rest)_.",
        "",
        *(f"- {line}" for line in data["lines"]),
        "",
        "_Antwoorden (answers):_ " + " · ".join(
            f"{i}. {a}" for i, a in enumerate(data["answers"], 1)
        ),
    ]
    return "\n".join(out)
