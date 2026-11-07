# tests/league/test_team_facts.py
"""What the UI says about a team's city: market size and climate."""

from src.league import team_facts, team_pool


def test_every_pool_team_has_named_facts():
    for t in team_pool.TEAM_POOL:
        f = team_facts.facts(t.city, t.mascot)
        assert f["market_name"] in ("Small", "Modest", "Mid-size", "Big", "Huge")
        assert f["climate_name"] in team_facts.CLIMATE_NAMES.values()


def test_temperate_reads_as_mild():
    assert team_facts.short("London", "Lions") == "Huge · Mild"


def test_a_renamed_team_falls_back_to_its_city():
    assert team_facts.short("Boston", "Beans") == "Mid-size · Cold"
    assert team_facts.facts("Denver", "Beans") is None


def test_market_rank_counts_ties():
    assert team_facts.market_rank(5, [5, 4, 3]) == (1, False)
    assert team_facts.market_rank(3, [5, 5, 3, 3]) == (3, True)
