# src/game/win_expectancy.py
"""
Win expectancy and run expectancy, for WPA and RE24.

Both come from one table, data/run_expectancy.json: for each of the 24
base-out states, how often the batting team goes on to score 0, 1, 2 ...
runs before the half-inning ends. scripts/build_run_expectancy.py makes it
from simulated seasons, so it matches this engine, not MLB.

  run_expectancy(bases, outs)   runs the batting team should still score
  home_win_prob(...)            the home team's chance of winning from a
                                game state, worked out inning by inning
                                from the same run distributions (extra
                                innings start with the ghost runner on
                                second when the game uses one)

Bases are a 3-bit mask: 1 = runner on first, 2 = second, 4 = third.
"""

from __future__ import annotations

import json
from functools import lru_cache, cache
from pathlib import Path

_DATA = Path(__file__).parent / "data" / "run_expectancy.json"
REGULATION = 9
MAX_DIFF = 25  # score margins beyond this count as this
MAX_INNING = 30  # past this, a tied game is a coin flip

SECOND_ONLY = 2


@lru_cache(maxsize=1)
def _table() -> dict[tuple[int, int], tuple[float, ...]]:
    raw = json.loads(_DATA.read_text())
    return {
        (int(k.split(",")[0]), int(k.split(",")[1])): tuple(v)
        for k, v in raw["dist"].items()
    }


def run_dist(bases: int, outs: int) -> tuple[float, ...]:
    """P(0 runs), P(1 run) ... to the end of the half-inning; the last entry
    is that many runs or more."""
    return _table()[(bases, outs)]


def run_expectancy(bases: int, outs: int) -> float:
    if outs >= 3:
        return 0.0
    return sum(r * p for r, p in enumerate(run_dist(bases, outs)))


def _clamp(d: int) -> int:
    return max(-MAX_DIFF, min(MAX_DIFF, d))


def _start_dist(inning: int, ghost: bool) -> tuple[float, ...]:
    if ghost and inning > REGULATION:
        return run_dist(SECOND_ONLY, 0)
    return run_dist(0, 0)


def _after_bottom(inning: int, diff: int, runs: int, ghost: bool) -> float:
    """Home's chance once the bottom of `inning` ends (or walks off) with
    home scoring `runs` more; diff is home minus away before them."""
    d = diff + runs
    if inning >= REGULATION:
        if d > 0:
            return 1.0
        if d < 0:
            return 0.0
    return _start_top(inning + 1, _clamp(d), ghost)


@cache
def _start_bottom(inning: int, diff: int, ghost: bool) -> float:
    if inning >= REGULATION and diff > 0:
        return 1.0  # the bottom half isn't played
    return sum(
        p * _after_bottom(inning, diff, r, ghost)
        for r, p in enumerate(_start_dist(inning, ghost))
    )


@cache
def _start_top(inning: int, diff: int, ghost: bool) -> float:
    if inning > MAX_INNING:
        return 0.5 if diff == 0 else (1.0 if diff > 0 else 0.0)
    return sum(
        p * _start_bottom(inning, _clamp(diff - r), ghost)
        for r, p in enumerate(_start_dist(inning, ghost))
    )


def home_win_prob(
    inning: int, top: bool, outs: int, bases: int, diff: int, ghost: bool = False
) -> float:
    """The home team's chance of winning with `outs` out and `bases`
    occupied in the top or bottom of `inning`, home ahead by `diff` (behind
    when negative). outs of 3 means the half-inning just ended."""
    diff = _clamp(diff)
    if outs >= 3:
        if top:
            return _start_bottom(inning, diff, ghost)
        return _after_bottom(inning, diff, 0, ghost)
    dist = run_dist(bases, outs)
    if top:
        return sum(
            p * _start_bottom(inning, _clamp(diff - r), ghost)
            for r, p in enumerate(dist)
        )
    return sum(p * _after_bottom(inning, diff, r, ghost) for r, p in enumerate(dist))
