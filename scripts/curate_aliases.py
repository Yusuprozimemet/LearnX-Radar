"""Run one autonomous alias-curation pass and apply it — no human gate.

Pipeline (see radar/alias_curator.py): embed the accrued skill vocabulary, shortlist
near-duplicate name pairs by cosine, let the NIM LLM judge which are truly the same
skill (conservatively), then MERGE the accepted ones into storage/skill_aliases.json
so the next radar run collapses them. Every decision (merge AND keep-separate, with
the model's reason) is appended to storage/skill_aliases_log.md, and a short summary
is DM'd to the owner on Telegram. Nothing blocks the daily lesson: this commits its
result and moves on; the human reviews the log/commit later and reverts if wrong.

Meant to run ~weekly (own routine, or main.py gated on a weekly check). It only ever
proposes pairs not already aliased, so re-runs converge to "no change".

  python -m scripts.curate_aliases            # judge, apply, log, notify
  python -m scripts.curate_aliases --nim      # use NIM embeddings to shortlist
  python -m scripts.curate_aliases --dry-run  # judge + print, persist nothing
"""
import sys
from datetime import date

from learnx import llm
from radar.alias_curator import curate
from radar.semantic_match import lexical_embedder, nim_embedder
from storage import load_learned_aliases, load_trending_history, save_learned_aliases
from storage.state import _DIR

LOG_FILE = _DIR / "skill_aliases_log.md"


def _append_log(decisions: list[dict], applied: dict[str, str]) -> None:
    merged = [d for d in decisions if d["merge"]]
    kept = [d for d in decisions if not d["merge"]]
    lines = [f"\n## {date.today().isoformat()} — {len(applied)} new alias(es)\n"]
    for d in merged:
        flag = "" if (d["b"] if d["canonical"] == d["a"] else d["a"]) in applied else " (dup)"
        lines.append(f"- MERGE `{d['a']}` + `{d['b']}` -> `{d['canonical']}` "
                     f"(cos {d['cosine']}){flag} — {d['reason']}")
    for d in kept:
        lines.append(f"- keep `{d['a']}` / `{d['b']}` separate "
                     f"(cos {d['cosine']}) — {d['reason']}")
    LOG_FILE.write_text(
        (LOG_FILE.read_text(encoding="utf-8") if LOG_FILE.exists() else
         "# Learned skill aliases — autonomous curation log\n")
        + "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def _notify(applied: dict[str, str], kept: int) -> None:
    if not applied:
        return
    from delivery.telegram_sender import send_report
    body = "\n".join(f"• {v}  ⟵  {k}" for k, v in applied.items())
    send_report(f"🔗 Learned {len(applied)} skill alias(es) ({kept} pairs kept separate):"
                f"\n{body}\n\nSee storage/skill_aliases_log.md")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    dry = "--dry-run" in sys.argv
    use_nim = "--nim" in sys.argv
    embedder = nim_embedder() if use_nim else lexical_embedder
    threshold = 0.80 if use_nim else 0.60

    history = load_trending_history()
    if not history:
        print("no trending history yet — nothing to curate")
        return

    result = curate(history, chat_fn=llm.chat, embedder=embedder, threshold=threshold)
    decisions, new_aliases = result["decisions"], result["aliases"]

    print(f"{len(decisions)} pair(s) judged; {len(new_aliases)} accepted as merges:\n")
    for d in decisions:
        verb = f"MERGE -> {d['canonical']}" if d["merge"] else "keep separate"
        print(f"  [{d['cosine']:.3f}] {d['a']} | {d['b']}  =>  {verb}")
        print(f"           {d['reason']}")

    if dry:
        print("\n--dry-run: nothing written.")
        return

    existing = load_learned_aliases()
    applied = {k: v for k, v in new_aliases.items() if k not in existing}
    if applied:
        existing.update(applied)
        save_learned_aliases(existing)
    _append_log(decisions, applied)
    _notify(applied, sum(1 for d in decisions if not d["merge"]))
    print(f"\napplied {len(applied)} new alias(es); "
          f"{len(load_learned_aliases())} learned total. Log: {LOG_FILE.name}")


if __name__ == "__main__":
    main()
