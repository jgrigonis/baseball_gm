# scripts/draft_strategy_preview.py
"""
Sanity-check the draft strategy math against a freshly generated pool.

For a few strategies, prints the top players by strategy score and the first
picks a team would make from one draft slot, with every other team taking the
best prospect rating. Nothing touches the database.

    uv run python -m scripts.draft_strategy_preview --teams 24 --slot 7 --seed 1
"""

import argparse
import random

from src.league.offseason.draft_generator import DraftGenerator
from src.league.offseason.draft_strategy import (
    CHIPS,
    HIGH,
    MED,
    DraftStrategy,
    StrategyScorer,
    project_picks,
)
from src.league.offseason.snake_draft import ROUNDS
from src.player.player_evaluator import PlayerEvaluator

STRATEGIES = {
    "Best available": DraftStrategy(),
    "Need IF (High)": DraftStrategy(chips={"if": HIGH}),
    "Need C + RP (Med)": DraftStrategy(chips={"c": MED, "rp": MED}),
    "Power + Ace SP (High)": DraftStrategy(chips={"power": HIGH, "ace_sp": HIGH}),
    "Upside": DraftStrategy(age_pref=-1.0),
    "Ready sooner": DraftStrategy(age_pref=1.0),
}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--teams", type=int, default=24)
    ap.add_argument("--slot", type=int, default=7, help="your round-1 pick (1-based)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--picks", type=int, default=5)
    args = ap.parse_args()

    pool = DraftGenerator(None, random.Random(args.seed))._generate_prospects()
    rated = sorted(
        ((p, PlayerEvaluator.prospect_rating(p.skills)) for p in pool),
        key=lambda x: x[1],
        reverse=True,
    )
    scorer = StrategyScorer(rated)
    by_id = {p.id: p for p, _ in rated}
    rank = {pid: i + 1 for i, pid in enumerate(scorer.order)}

    def describe(pid: str) -> str:
        p = by_id[pid]
        fits = " ".join(
            f"{CHIPS[k].label}={v:.1f}" for k, v in scorer.fits[pid].items() if v > 0
        )
        return (
            f"#{rank[pid]:<4} {p.name:<22} {p.position:<3} age {p.age}"
            f"  prospect {scorer.prospect[pid]:>3}  {fits}"
        )

    teams = [f"t{i}" for i in range(1, args.teams + 1)]
    me = teams[args.slot - 1]

    for name, strategy in STRATEGIES.items():
        print(f"\n=== {name} ===")
        avail = set(scorer.order)
        top = sorted(avail, key=lambda pid: -scorer.score(pid, strategy))
        print(f"Top {args.top} by score (#n = rank by prospect rating):")
        for pid in top[: args.top]:
            print(f"  {scorer.score(pid, strategy):5.1f}  {describe(pid)}")
        print(f"Projected first {args.picks} picks from slot {args.slot}:")
        for overall, pid in project_picks(
            scorer, teams, ROUNDS, {me: strategy}, me, args.picks
        ):
            print(f"  pick {overall:>3}  {describe(pid)}")


if __name__ == "__main__":
    main()
