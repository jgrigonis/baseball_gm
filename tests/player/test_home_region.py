# tests/player/test_home_region.py
from collections import Counter

from src.league.team_pool import REGIONS, TEAM_POOL
from src.player.home_region import home_region_for


def test_a_players_home_region_is_the_same_every_time():
    assert home_region_for("p-123") == home_region_for("p-123")


def test_home_regions_follow_the_team_pools_mix():
    got = Counter(home_region_for(f"p{i}") for i in range(20000))
    assert set(got) == set(REGIONS)
    pool = Counter(t.region for t in TEAM_POOL)
    for region in REGIONS:
        share = pool[region] / len(TEAM_POOL)
        assert abs(got[region] / 20000 - share) < 0.02, region
