"""Experiment: choose GROUNDING_READ_TOP_N from measured data, not a guess.

Sweeps the read budget N across a few real chosen skills and measures the
quality vs. latency trade-off (spec: specs/v7/day24-brief-grounding.md). For each
(skill, N) it times the grounding step (Exa + Jina reads) and the brief LLM call
separately, records context size, and writes the brief markdown so the quality at
each N can be read side by side.

Run from the repo root:  python -m scripts.exp_grounding
Outputs: output/exp_grounding/{skill}__N{n}.md  and  summary.md
Deletable — not part of the cron pipeline.
"""
import sys
import time
from pathlib import Path

import config
from radar import brief_writer, gap_scorer, research, skill_extractor
from radar.prompt_loader import load_prompt
from storage import slugify

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SWEEP = [0, 2, 3, 5, 8]      # N=0 is the ungrounded baseline
N_SKILLS = 3                 # distinct top skills to test
OUT = Path("output/exp_grounding")
EMPTY_MEMORY = {"version": 1, "skills": {}}

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
    def _tokens(s: str) -> int:
        return len(_ENC.encode(s))
except ImportError:
    def _tokens(s: str) -> int:
        return len(s) // 4


def _latest_items() -> list[dict]:
    import json
    dumps = sorted(Path("output").glob("source_test_*.json"))
    if not dumps:
        sys.exit("No output/source_test_*.json found — run a scrape dump first.")
    data = json.loads(dumps[-1].read_text(encoding="utf-8"))
    print(f"Loaded {data['total']} items from {dumps[-1].name}")
    return data["items"]


def _pick_skills(items: list[dict]) -> list[dict]:
    """Real top skills from today's corpus (one extract + score pass)."""
    mentions = skill_extractor.extract(items)
    profile = {"known": config.KNOWN_SKILLS, "goals": config.LEARNING_GOALS}
    scored = gap_scorer.score(mentions, EMPTY_MEMORY, profile)
    picks = scored[:N_SKILLS]
    print("Skills under test:", [s["skill"] for s in picks])
    return picks


class _CountingReader:
    """Wraps the Jina reader to count attempts/successes for the metrics."""

    def __init__(self):
        self.attempts = self.ok = 0

    def __call__(self, url: str):
        self.attempts += 1
        item = research.web.read(url)
        if item:
            self.ok += 1
        return item


def main() -> None:
    config.validate()
    OUT.mkdir(parents=True, exist_ok=True)
    items = _latest_items()
    skills = _pick_skills(items)

    rows = []
    for skill in skills:
        for n in SWEEP:
            config.GROUNDING_READ_TOP_N = n
            reader = _CountingReader()

            t0 = time.perf_counter()
            selected = brief_writer._select_sources(skill, items, reader=reader)
            grounding = (
                research.format_context(selected, config.GROUNDING_TEXT_CHARS)
                if selected else ""
            )
            t_ground = time.perf_counter() - t0

            prompt = load_prompt("brief.txt").format(
                skill=skill["skill"],
                evidence=skill.get("evidence", ""),
                sources=", ".join(skill.get("sources", [])) or "multiple sources",
                prior_context=brief_writer._prior_context(EMPTY_MEMORY, skill["skill"]),
                grounding=grounding or brief_writer._NO_GROUNDING,
            )
            from learnx.llm import chat
            t1 = time.perf_counter()
            try:
                brief = chat([{"role": "user", "content": prompt}], max_tokens=1500).strip()
            except Exception as exc:
                brief = f"(brief failed: {exc})"
            brief += brief_writer._sources_section(selected)
            t_brief = time.perf_counter() - t1

            cites = brief.count("[1]") + brief.count("[2]") + brief.count("[3]")
            path = OUT / f"{slugify(skill['skill'])}__N{n}.md"
            path.write_text(brief, encoding="utf-8")

            row = {
                "skill": skill["skill"], "N": n,
                "reads_ok": f"{reader.ok}/{reader.attempts}",
                "ctx_tokens": _tokens(grounding),
                "ground_s": round(t_ground, 1),
                "brief_s": round(t_brief, 1),
                "total_s": round(t_ground + t_brief, 1),
                "has_cite": "yes" if cites else "no",
            }
            rows.append(row)
            print(f"  {skill['skill'][:24]:24} N={n}  reads={row['reads_ok']:>5}  "
                  f"ctx={row['ctx_tokens']:>5}t  ground={row['ground_s']:>4}s  "
                  f"brief={row['brief_s']:>4}s  cite={row['has_cite']}")

    # Markdown summary table for the spec.
    hdr = "| skill | N | reads ok | ctx tokens | ground s | brief s | total s | cites |"
    sep = "|---|---|---|---|---|---|---|---|"
    lines = ["# Grounding read-budget experiment", "", hdr, sep]
    for r in rows:
        lines.append(
            f"| {r['skill']} | {r['N']} | {r['reads_ok']} | {r['ctx_tokens']} | "
            f"{r['ground_s']} | {r['brief_s']} | {r['total_s']} | {r['has_cite']} |"
        )
    (OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {OUT/'summary.md'} and {len(rows)} briefs to {OUT}/")


if __name__ == "__main__":
    main()
