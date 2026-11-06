# scripts/build_run_expectancy.py
"""
Build src/game/data/run_expectancy.json, the run distributions behind WPA
and RE24 (src/game/win_expectancy.py), from simulated seasons.

For every plate appearance it notes the base-out state and how many more
runs the batting team scored before the half-inning ended. Half-innings a
walk-off cut short are left out.

    # play 1 fresh 30-team season in a scratch database and write the table
    DATABASE_URL=postgresql://... uv run python -m scripts.build_run_expectancy --sim 1

    # merge counts saved by earlier runs (--save) into one table
    uv run python -m scripts.build_run_expectancy --merge a.json b.json

Re-run it after engine changes that move scoring (see
scripts/league_stat_check.py).
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from src.game import game as game_module

OUT = Path(__file__).resolve().parent.parent / "src/game/data/run_expectancy.json"
MAX_RUNS = 10  # the last bucket is this many or more


def collect(n_seasons: int) -> dict[str, list[int]]:
    """Play n seasons and count runs-to-end-of-half from each state."""
    from scripts.calibrate_backstory import sim_season
    from src.db.connection import get_connection
    from src.db.init import init_db

    counts: dict[str, list[int]] = defaultdict(lambda: [0] * (MAX_RUNS + 1))
    Game = game_module.Game
    seg_state = Game._seg_state
    play = Game.play

    def watched_seg_state(self):
        state = seg_state(self)
        if self._seg is None:  # a plate appearance is starting
            inning, top = self.inning.number, self.inning.top
            so_far = self.score.runs_in_inning(inning, top=top)
            self._re_starts.append((inning, top, state[2], state[3], so_far))
        return state

    def watched_play(self):
        self._re_starts = []
        result = play(self)
        last = (self.inning.number, self.inning.top)
        walked_off = not self.inning.top and self.inning.outs < 3
        for inning, top, outs, bases, so_far in self._re_starts:
            if walked_off and (inning, top) == last:
                continue
            total = self.score.runs_in_inning(inning, top=top)
            counts[f"{bases},{outs}"][min(MAX_RUNS, total - so_far)] += 1
        return result

    Game._seg_state = watched_seg_state
    Game.play = watched_play
    with get_connection() as conn:
        init_db(conn)
        for i in range(n_seasons):
            print(f"Playing season {i + 1} of {n_seasons}...", flush=True)
            sim_season(conn)
    return dict(counts)


def write(counts: dict[str, list[int]]) -> None:
    dist = {}
    for outs in range(3):
        for bases in range(8):
            c = counts.get(f"{bases},{outs}") or [1] + [0] * MAX_RUNS
            n = sum(c)
            dist[f"{bases},{outs}"] = [round(x / n, 6) for x in c]
    n_pa = sum(sum(c) for c in counts.values())
    OUT.write_text(
        json.dumps(
            {
                "source": f"scripts/build_run_expectancy.py, {n_pa} plate appearances",
                "dist": dist,
            },
            indent=1,
        )
        + "\n"
    )
    print(f"Wrote {OUT} from {n_pa} plate appearances")
    for outs in range(3):
        row = [sum(r * p for r, p in enumerate(dist[f"{b},{outs}"])) for b in range(8)]
        print(f"{outs} out: " + " ".join(f"{x:.2f}" for x in row))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sim", type=int, default=0, help="seasons to play")
    ap.add_argument("--save", help="also save the raw counts to this file")
    ap.add_argument("--merge", nargs="*", help="raw count files to add in")
    args = ap.parse_args()
    counts: dict[str, list[int]] = defaultdict(lambda: [0] * (MAX_RUNS + 1))
    if args.sim:
        for k, c in collect(args.sim).items():
            counts[k] = [a + b for a, b in zip(counts[k], c)]
        if args.save:
            Path(args.save).write_text(json.dumps(dict(counts)))
    for f in args.merge or []:
        for k, c in json.loads(Path(f).read_text()).items():
            counts[k] = [a + b for a, b in zip(counts[k], c)]
    write(dict(counts))


if __name__ == "__main__":
    main()
