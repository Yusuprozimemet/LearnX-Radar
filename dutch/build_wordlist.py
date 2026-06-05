"""ONE-TIME generator for dutch/wordlist.json — NOT part of the daily pipeline.

Run manually to draft new batches of curated words, then HUMAN-REVIEW the output
(check de/het, spelling, level) before the file is committed. The daily run never
calls this; it only reads the frozen, reviewed wordlist.json. Append-only by design:
existing ids are kept as-is, so re-running only adds new words.

    python -m dutch.build_wordlist --theme everyday --cefr A2 --count 40

Requires NVIDIA_API_KEY (same LLM client as the rest of the app).
"""
import argparse
import json
import re
import sys
from pathlib import Path

from dutch.wordlist import WORDLIST_FILE, load
from learnx.llm import chat, parse_json_response

_PROMPT = """You are compiling a vocabulary list for a CEFR {cefr} Dutch learner.
Produce {count} common, distinct Dutch words on the theme "{theme}".
For each word return JSON with: "nl" (the word; for nouns include the article de/het),
"en" (English gloss; for nouns "the ..."), "pos" ("noun"|"verb"|"adjective"|"adverb").
No proper nouns, no rare words, no duplicates. Return ONLY a JSON array, e.g.:
[{{"nl": "de afspraak", "en": "the appointment", "pos": "noun"}}]
"""


def _slug(nl: str) -> str:
    """Stable id from the headword (drop article, lowercase, alnum)."""
    head = re.sub(r"^(de|het)\s+", "", nl.strip().lower())
    return re.sub(r"[^a-z0-9]+", "-", head).strip("-")


def generate(theme: str, cefr: str, count: int, chat_fn=chat) -> list[dict]:
    raw = chat_fn(
        [{"role": "user", "content": _PROMPT.format(theme=theme, cefr=cefr, count=count)}],
        max_tokens=2000,
    )
    data = parse_json_response(raw)
    out: list[dict] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict) or not item.get("nl"):
            continue
        out.append(
            {
                "id": _slug(item["nl"]),
                "nl": item["nl"].strip(),
                "en": (item.get("en") or "").strip(),
                "pos": (item.get("pos") or "noun").strip(),
                "theme": theme,
                "cefr": cefr,
            }
        )
    return out


def merge(existing: list[dict], generated: list[dict]) -> list[dict]:
    """Append only words whose id is not already present (existing entries win)."""
    seen = {w["id"] for w in existing}
    added = [w for w in generated if w["id"] and w["id"] not in seen]
    return existing + added


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Draft new words for dutch/wordlist.json")
    ap.add_argument("--theme", default="everyday")
    ap.add_argument("--cefr", default="A2")
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--dry-run", action="store_true", help="print to stdout, don't write")
    args = ap.parse_args(argv)

    existing = load()
    generated = generate(args.theme, args.cefr, args.count)
    merged = merge(existing, generated)
    added = len(merged) - len(existing)
    payload = {"version": 1, "words": merged}
    text = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.dry_run:
        sys.stdout.write(text + "\n")
        sys.stderr.write(f"\n[dry-run] would add {added} new word(s)\n")
        return
    Path(WORDLIST_FILE).write_text(text + "\n", encoding="utf-8")
    sys.stderr.write(
        f"Added {added} new word(s) -> {WORDLIST_FILE}. "
        "NOW REVIEW de/het, spelling, and level before committing.\n"
    )


if __name__ == "__main__":
    main()
