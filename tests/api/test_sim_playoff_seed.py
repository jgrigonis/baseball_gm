# tests/api/test_sim_playoff_seed.py
"""sim_playoff seeds its RNG from the global one, like sim_next_day, so a
seeded run replays the playoffs exactly."""

import random
from unittest.mock import MagicMock, patch

import pytest

from src.api.services import sim_playoff as mod


class _Stop(Exception):
    pass


def _seed_used(global_seed: int) -> int:
    """Run sim_playoff up to the point it builds its RNG; return the seed."""
    seen = []

    def fake_random(seed=None):
        seen.append(seed)
        raise _Stop

    random.seed(global_seed)
    with (
        patch.object(mod, "LeagueRepository") as lr,
        patch.object(mod.random, "Random", side_effect=fake_random),
    ):
        lr.return_value.get_by_id.return_value = {"state": "playoffs"}
        with pytest.raises(_Stop):
            mod.sim_playoff("L", MagicMock())
    return seen[0]


def test_same_global_seed_replays_the_playoffs():
    seed = _seed_used(42)
    assert isinstance(seed, int)
    assert _seed_used(42) == seed
