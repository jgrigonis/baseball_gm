# src/league/team_pool.py
"""
Every team a league can play with. Each has a region and its city's
longitude:

- The longitude puts the teams in order around the globe (the Americas,
  Europe, West Asia, Asia, Oceania, and back), which is how leagues and
  divisions are cut (src/league/divisions.py): neighbors play together.
- The region names the divisions, and keeps a league's draw balanced
  (draw), so no league is mostly one corner of the world.

A league starts with a balanced draw of num_teams of them, and a person in
the lobby can bring in any other one (src/api/services/lobby_teams.py).
Every new league generates fresh rosters for its teams.

A team added here also wants colors (src/team/colors.py) and a uniform set
(src/web/static/img/uniforms/); without them it gets a fallback palette and
no uniforms on the Meet your team screen.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass

# The name `cligr new-league` gives the league it makes.
LEAGUE_NAME = "World League"

NORTH_AMERICA = "North America"
SOUTH_AMERICA = "South America"
EUROPE = "Europe"
WEST_ASIA = "West Asia"
SOUTHEAST_ASIA = "Southeast Asia"
EAST_ASIA = "East Asia"
OCEANIA = "Oceania"


@dataclass(frozen=True)
class PoolTeam:
    city: str
    mascot: str
    region: str
    longitude: float  # of the city, degrees east

    @property
    def key(self) -> tuple[str, str]:
        return (self.city, self.mascot)


TEAM_POOL: tuple[PoolTeam, ...] = (
    PoolTeam("New York", "Titans", NORTH_AMERICA, -74.0),
    PoolTeam("Chicago", "Blizzards", NORTH_AMERICA, -87.6),
    PoolTeam("Toronto", "Sentinels", NORTH_AMERICA, -79.4),
    PoolTeam("Los Angeles", "Stars", NORTH_AMERICA, -118.2),
    PoolTeam("San Francisco", "Seals", NORTH_AMERICA, -122.4),
    PoolTeam("Seattle", "Rain", NORTH_AMERICA, -122.3),
    PoolTeam("Portland", "Weird", NORTH_AMERICA, -122.7),
    PoolTeam("Mexico City", "Aztecs", NORTH_AMERICA, -99.1),
    PoolTeam("São Paulo", "Bandeirantes", SOUTH_AMERICA, -46.6),
    PoolTeam("Buenos Aires", "Matadors", SOUTH_AMERICA, -58.4),
    PoolTeam("London", "Lions", EUROPE, -0.1),
    PoolTeam("Dublin", "Shamrocks", EUROPE, -6.3),
    PoolTeam("Lisbon", "Navigators", EUROPE, -9.1),
    PoolTeam("Madrid", "Conquistadors", EUROPE, -3.7),
    PoolTeam("Paris", "Musketeers", EUROPE, 2.4),
    PoolTeam("Amsterdam", "Captains", EUROPE, 4.9),
    PoolTeam("Frankfurt", "Eagles", EUROPE, 8.7),
    PoolTeam("Milan", "Serpents", EUROPE, 9.2),
    PoolTeam("Rome", "Gladiators", EUROPE, 12.5),
    PoolTeam("Berlin", "Bear", EUROPE, 13.4),
    PoolTeam("Vienna", "Maestros", EUROPE, 16.4),
    PoolTeam("Warsaw", "Hussars", EUROPE, 21.0),
    PoolTeam("Istanbul", "Sultans", WEST_ASIA, 29.0),
    PoolTeam("Dubai", "Falcons", WEST_ASIA, 55.3),
    PoolTeam("Mumbai", "Mariners", WEST_ASIA, 72.9),
    PoolTeam("Bangkok", "Guardians", SOUTHEAST_ASIA, 100.5),
    PoolTeam("Singapore", "Merlions", SOUTHEAST_ASIA, 103.8),
    PoolTeam("Jakarta", "Garudas", SOUTHEAST_ASIA, 106.8),
    PoolTeam("Hong Kong", "Harbor Kings", EAST_ASIA, 114.2),
    PoolTeam("Beijing", "Dragons", EAST_ASIA, 116.4),
    PoolTeam("Shanghai", "Phoenix", EAST_ASIA, 121.5),
    PoolTeam("Seoul", "White Tigers", EAST_ASIA, 127.0),
    PoolTeam("Tokyo", "Samurai", EAST_ASIA, 139.7),
    PoolTeam("Sydney", "Sharks", OCEANIA, 151.2),
)

_BY_KEY = {t.key: t for t in TEAM_POOL}
_BY_CITY = {t.city: t for t in TEAM_POOL}


def get(city: str, mascot: str) -> PoolTeam | None:
    return _BY_KEY.get((city, mascot))


def by_city(city: str) -> PoolTeam | None:
    return _BY_CITY.get(city)


def draw(
    num_teams: int,
    rng: random.Random,
    keep: list[PoolTeam] | tuple[PoolTeam, ...] = (),
) -> list[PoolTeam]:
    """num_teams teams: the ones in ``keep``, then the rest drawn region by
    region, each region's share of the league in proportion to its share of
    the pool. Sorted by city."""
    picked = list(dict.fromkeys(keep))[:num_teams]
    taken = {t.key for t in picked}
    pool_counts = Counter(t.region for t in TEAM_POOL)
    counts = Counter(t.region for t in picked)
    left = {
        r: [t for t in TEAM_POOL if t.region == r and t.key not in taken]
        for r in pool_counts
    }
    while len(picked) < num_teams:
        open_regions = [r for r in left if left[r]]
        if not open_regions:
            break

        def owed(r):
            return num_teams * pool_counts[r] / len(TEAM_POOL) - counts[r]

        most = max(owed(r) for r in open_regions)
        region = rng.choice(sorted(r for r in open_regions if owed(r) == most))
        team = left[region].pop(rng.randrange(len(left[region])))
        picked.append(team)
        counts[region] += 1
    return sorted(picked, key=lambda t: t.city)


def closest(team: PoolTeam, candidates: list[PoolTeam]) -> PoolTeam | None:
    """The candidate most like ``team`` to swap it with: same region first,
    then nearest around the globe."""
    if not candidates:
        return None

    def distance(other):
        d = abs(team.longitude - other.longitude) % 360
        return (other.region != team.region, min(d, 360 - d), other.city)

    return min(candidates, key=distance)
