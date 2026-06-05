"""Experiment: choose MOMENTUM_WINDOW_DAYS from real history, not a guess.

Cross-day momentum needs accrued history to be meaningful — this harness reports,
for the most recent day, how the momentum multiplier and the would-be ranking
shift across candidate windows. With only a few days committed it prints a thin
result and says so; revisit once the cron has ~14+ days of post-Phase-2 history
(spec: specs/v7/day26).

Run from repo root:  python -m scripts.exp_momentum
Deletable — not part of the cron pipeline.
"""
import sys

import config
from radar import gap_scorer
from storage import load_trending_history

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

SWEEP = [7, 10, 14, 21]


def main() -> None:
    history = load_trending_history()
    days = sorted(history)
    print(f"history days available: {len(days)} ({days[:1]}..{days[-1:]})\n")
    if len(days) < 3:
        print("Too little history for a meaningful sweep — let the cron accrue ~14+ "
              "days of post-Phase-2 history, then re-run.")
        return

    latest = days[-1]
    rows = history[latest].get("scored", [])
    prior = {d: history[d] for d in days if d != latest}  # judge latest vs its past

    config.MOMENTUM_ENABLED = True
    for window in SWEEP:
        config.MOMENTUM_WINDOW_DAYS = window
        scored = []
        for r in rows:
            dw = r.get("demand_weight") or 0
            m = gap_scorer._momentum(r["skill"], dw, prior)
            scored.append((r["skill"], dw, m, dw * m))
        scored.sort(key=lambda x: -x[3])
        boosted = [s[0] for s in scored if s[2] > 1.0]
        damped = [s[0] for s in scored if s[2] < 1.0]
        print(f"window={window:>2}d  boosted={len(boosted)} damped={len(damped)}")
        for skill, dw, m, proxy in scored[:5]:
            print(f"    {skill[:28]:28} demand={dw:>4}  momentum={m:.3f}  proxy={proxy:.2f}")
        print()

    print("Decision: smallest window separating sustained risers from spikes without "
          "over-smoothing. Set config.MOMENTUM_WINDOW_DAYS + record rationale in the spec.")


if __name__ == "__main__":
    main()
