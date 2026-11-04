# src/league/team_pool.py
"""
Every team a league can play with. Each has a region and its city's
longitude:

- The longitude puts the teams in order around the globe (the Americas,
  Europe, West Asia, Asia, Oceania, and back), which is how leagues and
  divisions are cut (src/league/divisions.py): neighbors play together.
- The region names the divisions, and keeps a league's draw balanced
  (draw), so no league is mostly one corner of the world. Every player has
  a home region too (src/player/home_region.py).
- The market size and climate are for player happiness and, later, fans
  and money (plans/player-happiness.md, plans/owners.md).

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
REGIONS = (
    NORTH_AMERICA,
    SOUTH_AMERICA,
    EUROPE,
    WEST_ASIA,
    SOUTHEAST_ASIA,
    EAST_ASIA,
    OCEANIA,
)

# A city's climate, for players who'd rather play somewhere warm (or cold):
# its general reputation, not a season's weather.
TROPICAL = "tropical"
DESERT = "desert"
WARM = "warm"
TEMPERATE = "temperate"
COLD = "cold"
CLIMATES = (TROPICAL, DESERT, WARM, TEMPERATE, COLD)

# Market size, 1 (small) to 5 (huge): how much attention and money a team in
# that city draws. Mostly metro size, nudged by wealth and media reach, so a
# rich mid-sized city can rank with a bigger, poorer one. Player fame
# (plans/player-happiness.md) and fans and money (plans/owners.md) read it.
MIN_MARKET = 1
MAX_MARKET = 5


@dataclass(frozen=True)
class PoolTeam:
    city: str
    mascot: str
    region: str
    longitude: float  # of the city, degrees east
    market: int  # MIN_MARKET..MAX_MARKET
    climate: str  # one of CLIMATES

    @property
    def key(self) -> tuple[str, str]:
        return (self.city, self.mascot)


TEAM_POOL: tuple[PoolTeam, ...] = (
    PoolTeam("Boston", "Beacons", NORTH_AMERICA, -71.1, 3, COLD),
    PoolTeam("New York", "Titans", NORTH_AMERICA, -74.0, 5, TEMPERATE),
    PoolTeam("Chicago", "Blizzards", NORTH_AMERICA, -87.6, 4, COLD),
    PoolTeam("Toronto", "Sentinels", NORTH_AMERICA, -79.4, 3, COLD),
    PoolTeam("Los Angeles", "Stars", NORTH_AMERICA, -118.2, 5, WARM),
    PoolTeam("San Francisco", "Seals", NORTH_AMERICA, -122.4, 3, TEMPERATE),
    PoolTeam("Seattle", "Rain", NORTH_AMERICA, -122.3, 2, TEMPERATE),
    PoolTeam("Portland", "Weird", NORTH_AMERICA, -122.7, 1, TEMPERATE),
    PoolTeam("Mexico City", "Aztecs", NORTH_AMERICA, -99.1, 4, WARM),
    PoolTeam("São Paulo", "Bandeirantes", SOUTH_AMERICA, -46.6, 4, WARM),
    PoolTeam("Buenos Aires", "Matadors", SOUTH_AMERICA, -58.4, 3, WARM),
    PoolTeam("London", "Lions", EUROPE, -0.1, 5, TEMPERATE),
    PoolTeam("Dublin", "Shamrocks", EUROPE, -6.3, 1, TEMPERATE),
    PoolTeam("Lisbon", "Navigators", EUROPE, -9.1, 2, WARM),
    PoolTeam("Madrid", "Conquistadors", EUROPE, -3.7, 3, WARM),
    PoolTeam("Paris", "Musketeers", EUROPE, 2.4, 5, TEMPERATE),
    PoolTeam("Amsterdam", "Captains", EUROPE, 4.9, 2, TEMPERATE),
    PoolTeam("Frankfurt", "Eagles", EUROPE, 8.7, 2, TEMPERATE),
    PoolTeam("Milan", "Serpents", EUROPE, 9.2, 3, TEMPERATE),
    PoolTeam("Rome", "Gladiators", EUROPE, 12.5, 2, WARM),
    PoolTeam("Berlin", "Bear", EUROPE, 13.4, 3, TEMPERATE),
    PoolTeam("Vienna", "Maestros", EUROPE, 16.4, 2, TEMPERATE),
    PoolTeam("Warsaw", "Hussars", EUROPE, 21.0, 2, COLD),
    PoolTeam("Moscow", "Cossacks", EUROPE, 37.6, 4, COLD),
    PoolTeam("Istanbul", "Sultans", WEST_ASIA, 29.0, 4, TEMPERATE),
    PoolTeam("Cairo", "Pharaohs", WEST_ASIA, 31.2, 3, DESERT),
    PoolTeam("Dubai", "Falcons", WEST_ASIA, 55.3, 3, DESERT),
    PoolTeam("Mumbai", "Mariners", WEST_ASIA, 72.9, 4, TROPICAL),
    PoolTeam("Bangkok", "Guardians", SOUTHEAST_ASIA, 100.5, 3, TROPICAL),
    PoolTeam("Singapore", "Merlions", SOUTHEAST_ASIA, 103.8, 3, TROPICAL),
    PoolTeam("Jakarta", "Garudas", SOUTHEAST_ASIA, 106.8, 4, TROPICAL),
    PoolTeam("Hong Kong", "Harbor Kings", EAST_ASIA, 114.2, 4, WARM),
    PoolTeam("Beijing", "Dragons", EAST_ASIA, 116.4, 5, COLD),
    PoolTeam("Shanghai", "Phoenix", EAST_ASIA, 121.5, 5, WARM),
    PoolTeam("Seoul", "White Tigers", EAST_ASIA, 127.0, 4, COLD),
    PoolTeam("Tokyo", "Samurai", EAST_ASIA, 139.7, 5, TEMPERATE),
    PoolTeam("Sydney", "Sharks", OCEANIA, 151.2, 3, WARM),
    PoolTeam("Auckland", "Kiwis", OCEANIA, 174.8, 1, TEMPERATE),
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
    the pool, and every region at least one. Sorted by city."""
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
            # A region with no team yet goes first, so a small region like
            # Oceania (two teams) isn't squeezed out of a 16-team league.
            if not counts[r]:
                return float("inf")
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
