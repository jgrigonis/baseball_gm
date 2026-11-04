# src/player/home_region.py
"""
Where a player is from: one of the team pool's regions
(src/league/team_pool.py). Player happiness (plans/player-happiness.md) will
use it for the location drive: some players would rather play close to home.

It's drawn from the player's id, like his jersey numbers, so it's the same
whether it's made when he's created or backfilled later. Regions are drawn in
proportion to their share of the team pool, so the world's players come from
roughly where its teams are.
"""

from __future__ import annotations

import random
from collections import Counter

from src.league.team_pool import REGIONS, TEAM_POOL

_POOL_COUNTS = Counter(t.region for t in TEAM_POOL)
REGION_WEIGHTS: dict[str, int] = {r: _POOL_COUNTS[r] for r in REGIONS}


def random_home_region(rng: random.Random) -> str:
    regions = list(REGION_WEIGHTS)
    return rng.choices(regions, weights=[REGION_WEIGHTS[r] for r in regions])[0]


def home_region_for(player_id: str) -> str:
    """The player's home region, seeded by his id."""
    return random_home_region(random.Random(f"home-region:{player_id}"))
