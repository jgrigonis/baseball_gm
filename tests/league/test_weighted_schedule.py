# tests/league/test_weighted_schedule.py
import random
from collections import Counter
from datetime import date

import pytest

from src.league.schedule import ScheduleGenerator
from src.league.weighted_schedule import BLOCKS, WeightedSchedule


def _leagues(n: int) -> list[list[list[str]]]:
    per_league = n // 2
    divs = 3 if n == 30 else 2
    size = per_league // divs
    ids = [f"t{i}" for i in range(n)]
    return [
        [
            ids[c * per_league + d * size : c * per_league + (d + 1) * size]
            for d in range(divs)
        ]
        for c in range(2)
    ]


def _groups(leagues):
    where = {
        t: (c, d)
        for c, lg in enumerate(leagues)
        for d, div in enumerate(lg)
        for t in div
    }

    def group(x, y):
        if where[x] == where[y]:
            return "division"
        return "league" if where[x][0] == where[y][0] else "other"

    return group


@pytest.mark.parametrize("n", sorted(BLOCKS))
def test_every_team_plays_every_round_and_162_games(n):
    leagues = _leagues(n)
    rounds = WeightedSchedule(leagues, random.Random(n)).rounds(162)
    games = Counter()
    for pairs, length in rounds:
        teams = [t for p in pairs for t in p]
        assert len(teams) == len(set(teams)) == n
        assert length in (2, 3, 4)
        for h, v in pairs:
            games[h] += length
            games[v] += length
    assert set(games.values()) == {162}


@pytest.mark.parametrize("n", sorted(BLOCKS))
def test_division_rivals_play_most_and_the_other_league_least(n):
    leagues = _leagues(n)
    group = _groups(leagues)
    rounds = WeightedSchedule(leagues, random.Random(n)).rounds(162)
    pair_games = Counter()
    for pairs, length in rounds:
        for h, v in pairs:
            pair_games[frozenset((h, v))] += length
    by_group: dict[str, set[int]] = {"division": set(), "league": set(), "other": set()}
    for pair, g in pair_games.items():
        by_group[group(*pair)].add(g)
    # Every pair meets, division and league pairs all the same number of times.
    assert len(pair_games) == n * (n - 1) // 2
    assert len(by_group["division"]) == len(by_group["league"]) == 1
    assert min(by_group["division"]) > min(by_group["league"])
    assert max(by_group["other"]) <= min(by_group["league"])


def test_the_world_league_matches_the_plan():
    leagues = _leagues(30)
    group = _groups(leagues)
    rounds = WeightedSchedule(leagues, random.Random(1)).rounds(162)
    totals = Counter()
    for pairs, length in rounds:
        for h, v in pairs:
            if "t0" in (h, v):
                totals[group(h, v)] += length
    # 4 rivals x 13, 10 others in the league x 5, 15 in the other league x 4
    assert totals == {"division": 52, "league": 50, "other": 60}


@pytest.mark.parametrize("n", sorted(BLOCKS))
def test_home_games_come_close_to_half(n):
    rounds = WeightedSchedule(_leagues(n), random.Random(7)).rounds(162)
    home = Counter()
    for pairs, length in rounds:
        for h, _ in pairs:
            home[h] += length
    assert all(76 <= g <= 86 for g in home.values()), home


def test_create_schedule_with_leagues_is_weighted():
    leagues = _leagues(20)
    ids = [t for lg in leagues for div in lg for t in div]
    schedule = ScheduleGenerator(rng=random.Random(3)).create_schedule(
        season_id="S",
        team_ids=ids,
        start_date=date(2030, 4, 1),
        target_games=162,
        all_star_break_after=96,
        all_star_break_days=4,
        leagues=leagues,
    )
    played = Counter()
    for g in schedule:
        played[g.home_team_id] += 1
        played[g.away_team_id] += 1
    assert set(played.values()) == {162}
    # Division rivals t0 and t1 meet 13 times, t0 and t10 (other league) 6.
    meet = Counter(frozenset((g.home_team_id, g.away_team_id)) for g in schedule)
    assert meet[frozenset(("t0", "t1"))] == 13
    assert meet[frozenset(("t0", "t10"))] == 6
