# tests/league/test_team_pool.py
import random
from collections import Counter

import pytest

from src.league import team_pool
from src.league.team_pool import TEAM_POOL


def test_every_pool_team_is_unique():
    assert len({t.city for t in TEAM_POOL}) == len(TEAM_POOL)
    assert len({t.key for t in TEAM_POOL}) == len(TEAM_POOL)


@pytest.mark.parametrize("n", [16, 20, 24, 28, 30, 32])
def test_a_draw_is_the_size_asked_and_the_same_every_time(n):
    first = team_pool.draw(n, random.Random("L1"))
    assert len({t.key for t in first}) == n
    assert first == team_pool.draw(n, random.Random("L1"))


@pytest.mark.parametrize("n", [16, 24, 30])
def test_a_draw_takes_each_regions_share(n):
    pool = Counter(t.region for t in TEAM_POOL)
    for seed in range(20):
        got = Counter(t.region for t in team_pool.draw(n, random.Random(seed)))
        for region, size in pool.items():
            share = n * size / len(TEAM_POOL)
            assert share - 1 < got[region] < share + 1, (seed, region, got)


def test_kept_teams_are_always_in_the_draw():
    keep = [team_pool.get("Sydney", "Sharks"), team_pool.get("Dubai", "Falcons")]
    drawn = team_pool.draw(16, random.Random(3), keep=keep)
    assert set(keep) <= set(drawn)
    assert len(drawn) == 16


def test_every_team_turns_up_in_some_small_league():
    seen = set()
    for i in range(60):
        seen |= {t.key for t in team_pool.draw(16, random.Random(f"L{i}"))}
    assert seen == {t.key for t in TEAM_POOL}


def test_closest_prefers_the_same_region_then_the_nearest():
    berlin = team_pool.get("Berlin", "Bear")
    candidates = [
        team_pool.get("Istanbul", "Sultans"),  # nearer, other region
        team_pool.get("Lisbon", "Navigators"),
        team_pool.get("Warsaw", "Hussars"),
    ]
    assert team_pool.closest(berlin, candidates).city == "Warsaw"
    assert team_pool.closest(berlin, candidates[:1]).city == "Istanbul"
    assert team_pool.closest(berlin, []) is None


def test_closest_goes_the_short_way_around_the_globe():
    sydney = team_pool.get("Sydney", "Sharks")
    far = [team_pool.get("Seattle", "Rain"), team_pool.get("London", "Lions")]
    assert team_pool.closest(sydney, far).city == "Seattle"
