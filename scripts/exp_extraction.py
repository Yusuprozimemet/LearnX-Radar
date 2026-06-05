"""Experiment: choose EXTRACTION_CHUNK_TOKENS from measured data, not a guess.

Map-reduce attribution is deterministic (a corpus scan) regardless of chunking,
so chunk size only trades RECALL (candidates discovered) against COST (LLM calls
+ latency). This sweeps the chunk-token budget over the day's real corpus and
reports recall + cost so we pick the knee (spec: specs/v7/day25).

Run from repo root:  python -m scripts.exp_extraction
Outputs: output/exp_extraction/summary.md + candidates_*.txt per setting.
Deletable — not part of the cron pipeline.
"""
import json
import sys
import time
from pathlib import Path

import config
from radar import skill_extractor

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# chunk-token budgets to sweep; the big value ≈ single pass (one chunk).
SWEEP = [4000, 6000, 8000, 12000, 10_000_000]
OUT = Path("output/exp_extraction")


def _latest_items() -> list[dict]:
    dumps = sorted(Path("output").glob("source_test_*.json"))
    if not dumps:
        sys.exit("No output/source_test_*.json — run a scrape dump first.")
    data = json.loads(dumps[-1].read_text(encoding="utf-8"))
    print(f"Loaded {data['total']} items from {dumps[-1].name}\n")
    return data["items"]


class _CountingChat:
    """Wraps the real LLM call to count map invocations (and failures)."""

    def __init__(self):
        from learnx.llm import chat
        self._chat = chat
        self.calls = self.fails = 0

    def __call__(self, messages, **k):
        self.calls += 1
        try:
            return self._chat(messages, **k)
        except Exception:
            self.fails += 1
            raise


def main() -> None:
    config.validate()
    OUT.mkdir(parents=True, exist_ok=True)
    items = _latest_items()
    config.EXTRACTION_MAPREDUCE = True

    rows = []
    for budget in SWEEP:
        config.EXTRACTION_CHUNK_TOKENS = budget
        n_chunks = len(skill_extractor._chunk_by_tokens(items, budget))
        chat = _CountingChat()

        t0 = time.perf_counter()
        mentions = skill_extractor.extract(items, chat_fn=chat)
        wall = time.perf_counter() - t0

        avg_src = (
            round(sum(len(m["sources"]) for m in mentions) / len(mentions), 2)
            if mentions else 0
        )
        label = "≈single" if budget >= 1_000_000 else f"{budget // 1000}k"
        rows.append({
            "budget": label, "chunks": n_chunks, "llm_calls": chat.calls,
            "fails": chat.fails, "candidates": len(mentions),
            "avg_sources": avg_src, "wall_s": round(wall, 1),
        })
        names = sorted(m["skill"] for m in mentions)
        (OUT / f"candidates_{label}.txt").write_text("\n".join(names), encoding="utf-8")
        print(f"  budget={label:>8}  chunks={n_chunks}  calls={chat.calls} "
              f"(fails={chat.fails})  candidates={len(mentions):>3}  "
              f"avg_src={avg_src}  wall={round(wall,1)}s")

    hdr = "| chunk budget | chunks | LLM calls | fails | candidates | avg sources/skill | wall s |"
    sep = "|---|---|---|---|---|---|---|"
    lines = ["# Extraction chunk-size experiment", "",
             "_Attribution is deterministic, so chunk size trades recall vs cost._", "",
             hdr, sep]
    for r in rows:
        lines.append(
            f"| {r['budget']} | {r['chunks']} | {r['llm_calls']} | {r['fails']} | "
            f"{r['candidates']} | {r['avg_sources']} | {r['wall_s']} |"
        )
    (OUT / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"\nWrote {OUT/'summary.md'} + per-setting candidate lists.")


if __name__ == "__main__":
    main()
