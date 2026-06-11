"""Dev tool: preview a single lesson end-to-end, no scrape/deliver.

    # lesson from an existing brief (curriculum -> dialogue -> audio):
    python scripts/preview_lesson.py [brief_file] [difficulty]

    # regenerate the BRIEF first via the grounding pipeline, then the lesson:
    python scripts/preview_lesson.py --regen "<skill name>" [difficulty]

Defaults: latest brief in briefs/, difficulty from LESSON_DIFFICULTY_OVERRIDE.
--regen exercises brief_writer (Exa grounding + re-rank) so you can A/B how
grounding changes the brief; it pulls the skill's evidence/sources from
storage/last_scored.json when present. Writes the brief (regen only), the
transcript, and the MP3 into output/.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
from learnx import audio_builder, curriculum, dialogue
from radar import brief_writer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output"


def _find_scored_skill(name: str) -> dict:
    """Pull a scored skill dict (evidence/sources) from last_scored.json by name."""
    path = ROOT / "storage" / "last_scored.json"
    if not path.exists():
        return {"skill": name}
    data = json.loads(path.read_text(encoding="utf-8"))
    hits: list[dict] = []

    def walk(o: object) -> None:
        if isinstance(o, dict):
            if isinstance(o.get("skill"), str):
                hits.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    for h in hits:
        if h["skill"].lower() == name.lower():
            return h
    return {"skill": name}


def _build_brief(difficulty: str) -> tuple[str, str]:
    """--regen path: regenerate the brief through brief_writer, return (md, title)."""
    name = sys.argv[2]
    skill = _find_scored_skill(name)
    print(f"Regenerating brief for: {name}")
    print(f"  evidence: {skill.get('evidence', '(none)')!r}")
    print(f"  sources:  {skill.get('sources', [])}\n")
    # items=[] -> grounding leans entirely on Exa (the discourse-biased search),
    # which is exactly the lever under test here.
    brief_md = brief_writer.write(skill, memory={}, items=[])
    out = OUT / "preview-brief.md"
    OUT.mkdir(parents=True, exist_ok=True)
    out.write_text(brief_md, encoding="utf-8")
    print(f"Brief -> {out}\n")
    print("=== BRIEF ===\n")
    print(brief_md)
    print("\n=== /BRIEF ===\n")
    return brief_md, name


def main() -> None:
    regen = len(sys.argv) > 1 and sys.argv[1] == "--regen"
    difficulty = (sys.argv[3] if regen else (sys.argv[2] if len(sys.argv) > 2 else None)) or (
        config.LESSON_DIFFICULTY_OVERRIDE or config.LESSON_DIFFICULTY_DEFAULT
    )

    if regen:
        brief_md, title = _build_brief(difficulty)
    else:
        briefs = sorted((ROOT / "briefs").glob("*.md"))
        brief_path = Path(sys.argv[1]) if len(sys.argv) > 1 else briefs[-1]
        brief_md = brief_path.read_text(encoding="utf-8")
        title = brief_path.stem.split("-", 1)[-1].replace("-", " ")
        print(f"Brief:      {brief_path.name}")

    print(f"Title:      {title}")
    print(f"Difficulty: {difficulty}\n")

    units = curriculum.plan(brief_md, title, difficulty=difficulty)
    print(f"Planned {len(units)} units:")
    for u in units:
        print(f"  {u.unit}. {u.concept}  (~{u.word_budget}w, complexity {u.complexity})")
    print()

    action = brief_writer.action_step(brief_md)
    lines = dialogue.generate(units, title, action=action, difficulty=difficulty)

    transcript = "\n".join(f"{ln.speaker}: {ln.text}" for ln in lines)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "preview-transcript.txt").write_text(transcript, encoding="utf-8")
    print("=== TRANSCRIPT ===\n")
    print(transcript)
    print(f"\n=== {len(lines)} lines -> output/preview-transcript.txt ===")

    mp3 = str(OUT / f"preview-{difficulty}.mp3")
    asyncio.run(audio_builder.build(lines, mp3))
    print(f"MP3: {mp3}")


if __name__ == "__main__":
    main()
