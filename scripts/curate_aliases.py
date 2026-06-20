"""Run one autonomous alias-curation pass and apply it — no human gate.

Pipeline (see radar/alias_curator.py): embed the accrued skill vocabulary, shortlist
near-duplicate name pairs by cosine, let the NIM LLM judge which are truly the same
skill (conservatively), then MERGE the accepted ones into storage/skill_aliases.json
so the next radar run collapses them. Every decision (merge AND keep-separate, with
the model's reason) is appended to storage/skill_aliases_log.md, and a short summary
is DM'd to the owner on Telegram. Nothing blocks the daily lesson: this commits its
result and moves on; the human reviews the log/commit later and reverts if wrong.

Meant to run ~weekly. In a cloud routine the checkout is thrown away when the run
ends, so --commit makes the script carry its own result home: it commits the new
alias file + log straight to main and pushes. It only ever proposes pairs not
already aliased, so weeks with nothing new write nothing and commit nothing.

  python -m scripts.curate_aliases             # judge, apply, log, notify (no push)
  python -m scripts.curate_aliases --commit    # ...and commit+push to main (routine)
  python -m scripts.curate_aliases --nim       # use NIM embeddings to shortlist
  python -m scripts.curate_aliases --dry-run   # judge + print, persist nothing
  python -m scripts.curate_aliases --reject "claude code" "claude" [--commit]
                                               # durably overrule a merge: the pair
                                               # is denylisted so it's never re-proposed
"""
import subprocess
import sys
from datetime import date

from learnx import llm
from radar.alias_curator import curate
from radar.semantic_match import lexical_embedder, nim_embedder
from radar.skill_extractor import _canonical
from storage import (
    load_alias_denylist,
    load_learned_aliases,
    load_trending_history,
    save_alias_denylist,
    save_learned_aliases,
)
from storage.state import _DIR, ALIAS_DENYLIST_FILE, LEARNED_ALIASES_FILE

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


def _git_commit_push(files: list, msg: str) -> None:
    """Commit the given files to main and push. Used by the weekly routine, whose
    cloud checkout is otherwise discarded. Failures are surfaced, not fatal — the
    files are already saved; a human can commit them if the push is rejected."""
    paths = [str(p) for p in files if p.exists()]
    if not paths:
        return
    ident = ["-c", "user.name=Claude", "-c", "user.email=noreply@anthropic.com"]
    try:
        subprocess.run(["git", "add", *paths], check=True)  # noqa: S607
        subprocess.run(["git", *ident, "commit", "-m", msg], check=True)  # noqa: S607
        subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)  # noqa: S607
        print("committed and pushed to main.")
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"git step failed ({exc}); saved locally but NOT pushed.")


def _reject(name_a: str, name_b: str, *, commit: bool) -> None:
    """Durably overrule a merge: add the canonical pair to the denylist (and drop it
    from learned aliases if present) so the curator never re-proposes it."""
    a, b = _canonical(name_a), _canonical(name_b)
    deny = load_alias_denylist()
    deny.add(frozenset((a, b)))
    save_alias_denylist(deny)
    aliases = load_learned_aliases()
    removed = {k: v for k, v in aliases.items() if {k, v} == {a, b}}
    if removed:
        for k in removed:
            del aliases[k]
        save_learned_aliases(aliases)
    print(f"denylisted: '{a}' / '{b}' will never be merged"
          + (f"; removed existing alias {removed}" if removed else ""))
    if commit:
        msg = (f"chore(radar): keep '{a}' and '{b}' separate [skip ci]\n\n"
               "Human override; the curator will not re-propose this merge.\n\n"
               "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
        _git_commit_push([ALIAS_DENYLIST_FILE, LEARNED_ALIASES_FILE], msg)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    commit = "--commit" in sys.argv
    if "--reject" in sys.argv:
        i = sys.argv.index("--reject")
        _reject(sys.argv[i + 1], sys.argv[i + 2], commit=commit)
        return

    dry = "--dry-run" in sys.argv
    use_nim = "--nim" in sys.argv
    embedder = nim_embedder() if use_nim else lexical_embedder
    threshold = 0.80 if use_nim else 0.60

    history = load_trending_history()
    if not history:
        print("no trending history yet — nothing to curate")
        return

    denylist = load_alias_denylist()
    result = curate(history, chat_fn=llm.chat, embedder=embedder,
                    threshold=threshold, denylist=denylist)
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
    if not applied:
        print("\nno new aliases — nothing written or committed.")
        return

    existing.update(applied)
    save_learned_aliases(existing)
    _append_log(decisions, applied)
    _notify(applied, sum(1 for d in decisions if not d["merge"]))
    print(f"\napplied {len(applied)} new alias(es); {len(existing)} learned total. "
          f"Log: {LOG_FILE.name}")
    if commit:
        msg = ("chore(radar): learn skill alias(es) [skip ci]\n\n"
               + "\n".join(f"{v} <- {k}" for k, v in applied.items())
               + "\n\nAutonomous curation pass; see storage/skill_aliases_log.md for "
                 "the full verdicts.\n\nCo-Authored-By: Claude Opus 4.8 "
                 "<noreply@anthropic.com>")
        _git_commit_push([LEARNED_ALIASES_FILE, LOG_FILE], msg)


if __name__ == "__main__":
    main()
