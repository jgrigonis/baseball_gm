# src/league/divisions.py
"""
Leagues and divisions. Every league is split into two leagues, each split
into divisions of the same size: three divisions of five for 30 teams, two
for the other sizes (16, 20, 24, 28 or 32).

The split is by geography (src/league/team_pool.py): the teams go in order
around the globe by longitude, and the ring is cut into equal slices, the
first half one league and the second half the other, starting from
whichever point splits the fewest regions. Each division is named for the
region most of its teams are in, each league Atlantic or Pacific by which
side of the world it leans to. Teams outside the pool (a test team) are
drawn into divisions at random instead.

Standings group teams by division, the playoffs take each league's division
winners plus wild cards, and the weighted schedule setting plays division
rivals more often (src/league/weighted_schedule.py).

The split is kept in team_divisions, one row per team. Leagues started
before divisions existed have no rows, and everything falls back to one
table of all the teams.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field

from src.league import team_pool

# The team counts a league can be made with.
TEAM_COUNTS = (16, 20, 24, 28, 30, 32)
DEFAULT_TEAM_COUNT = 30

# Names for a random draw of teams outside the pool: (league, its divisions).
DRAW_NAMES = [
    ("Founders League", ["Red", "Gold", "Silver"]),
    ("Frontier League", ["Blue", "Green", "White"]),
]

ATLANTIC = "Atlantic League"
PACIFIC = "Pacific League"
# Which way a region leans, for naming the two leagues.
_LEAN = {
    team_pool.EUROPE: 1,
    team_pool.SOUTH_AMERICA: 1,
    team_pool.SOUTHEAST_ASIA: -1,
    team_pool.EAST_ASIA: -1,
    team_pool.OCEANIA: -1,
}
# Suffixes for divisions that would share a name, in ring order.
_SPLIT_NAMES = {2: ["West", "East"], 3: ["West", "Central", "East"]}

# Teams in the playoffs from each league.
PLAYOFF_TEAMS_PER_LEAGUE = 4


@dataclass
class Division:
    name: str
    team_ids: list[str] = field(default_factory=list)


@dataclass
class Conference:
    name: str
    divisions: list[Division] = field(default_factory=list)

    @property
    def team_ids(self) -> list[str]:
        return [t for d in self.divisions for t in d.team_ids]


def divisions_per_league(num_teams: int) -> int:
    """How many divisions each of the two leagues has; 0 when the teams
    don't split evenly (a test league)."""
    if num_teams == 30:
        return 3
    if num_teams and num_teams % 4 == 0:
        return 2
    return 0


def draw(teams: list[tuple[str, str]], rng: random.Random) -> list[Conference]:
    """Split the teams, as (team id, city), into two leagues of equal
    divisions: by geography when every city is in the team pool, otherwise
    at random. Empty, so no divisions, when they don't split evenly."""
    per_league = divisions_per_league(len(teams))
    if not per_league or len({tid for tid, _ in teams}) != len(teams):
        return []
    size = len(teams) // (2 * per_league)
    pool = [team_pool.by_city(city) for _, city in teams]
    if any(p is None for p in pool) or len({c for _, c in teams}) != len(teams):
        ids = [tid for tid, _ in teams]
        rng.shuffle(ids)
        return [
            Conference(
                name,
                [
                    Division(div_names[d], ids[(c * per_league + d) * size :][:size])
                    for d in range(per_league)
                ],
            )
            for c, (name, div_names) in enumerate(DRAW_NAMES)
        ]
    ring = sorted(zip(pool, (tid for tid, _ in teams)), key=lambda x: x[0].longitude)
    ring = _best_rotation(ring, size)
    slices = [ring[i : i + size] for i in range(0, len(ring), size)]
    names = _division_names([[p for p, _ in s] for s in slices])
    halves = []
    for c in range(2):
        mine = range(c * per_league, (c + 1) * per_league)
        lean = sum(_LEAN.get(p.region, 0) for d in mine for p, _ in slices[d])
        divs = [Division(names[d], [tid for _, tid in slices[d]]) for d in mine]
        halves.append((lean, divs))
    # The half leaning further toward the Atlantic is the Atlantic League.
    first, second = halves
    if second[0] > first[0]:
        first, second = second, first
    return [Conference(ATLANTIC, first[1]), Conference(PACIFIC, second[1])]


def _best_rotation(ring: list, size: int) -> list:
    """The ring, turned to start where cutting it into slices of ``size``
    puts the fewest different regions together: the fewest regions split
    between divisions and the fewest divisions mixing regions."""

    def cost(start):
        turned = ring[start:] + ring[:start]
        return sum(
            len({p.region for p, _ in turned[i : i + size]})
            for i in range(0, len(turned), size)
        )

    start = min(range(len(ring)), key=cost)
    return ring[start:] + ring[:start]


def _division_names(slices: list[list]) -> list[str]:
    """A name for each slice of the ring: the region most of its teams are
    in, or the two it's shared between. Names that come up more than once
    get West, Central or East, by where that region's teams in each lie."""
    names = []
    for teams in slices:
        top = Counter(p.region for p in teams).most_common()
        if len(top) == 1 or top[0][1] > top[1][1]:
            names.append(top[0][0])
        else:
            # A tie: the two regions, in ring order.
            pair = {top[0][0], top[1][0]}
            order = [p.region for p in teams if p.region in pair]
            names.append(" & ".join(dict.fromkeys(order)))
    out = list(names)
    for name, n in Counter(names).items():
        if n == 1:
            continue
        suffixes = _SPLIT_NAMES.get(n) or [str(i + 1) for i in range(n)]
        region = name.split(" & ")[0]

        def west_to_east(i):
            lons = sorted(p.longitude for p in slices[i] if p.region == region)
            return lons[len(lons) // 2]

        at = sorted((i for i, x in enumerate(names) if x == name), key=west_to_east)
        for i, suffix in zip(at, suffixes):
            out[i] = f"{name} {suffix}"
    return out


def save(conn, league_id: str, conferences: list[Conference]) -> None:
    conn.execute("DELETE FROM team_divisions WHERE league_id = %s", (league_id,))
    for c_order, conf in enumerate(conferences):
        for d_order, div in enumerate(conf.divisions):
            for team_id in div.team_ids:
                conn.execute(
                    """INSERT INTO team_divisions
                         (league_id, team_id, conference, division,
                          conference_order, division_order)
                       VALUES (%s, %s, %s, %s, %s, %s)""",
                    (league_id, team_id, conf.name, div.name, c_order, d_order),
                )


def load(conn, league_id: str) -> list[Conference]:
    """The league's leagues and divisions, in order. Empty for a league
    started before there were divisions."""
    rows = conn.execute(
        """SELECT td.team_id, td.conference, td.division
           FROM team_divisions td
           JOIN teams t ON t.id = td.team_id
           WHERE td.league_id = %s
           ORDER BY td.conference_order, td.division_order, t.city""",
        (league_id,),
    ).fetchall()
    out: list[Conference] = []
    for r in rows:
        if not out or out[-1].name != r["conference"]:
            out.append(Conference(r["conference"]))
        conf = out[-1]
        if not conf.divisions or conf.divisions[-1].name != r["division"]:
            conf.divisions.append(Division(r["division"]))
        conf.divisions[-1].team_ids.append(r["team_id"])
    return out


def schedule_leagues(conn, league_id: str) -> list[list[list[str]]] | None:
    """The split as the weighted schedule takes it, or None when the league
    plays a balanced schedule: the setting is off, or it has no divisions."""
    league = conn.execute(
        "SELECT weighted_schedule FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if not league or not league["weighted_schedule"]:
        return None
    confs = load(conn, league_id)
    if len(confs) != 2:
        return None
    return [[d.team_ids for d in c.divisions] for c in confs]


def playoff_order(
    conferences: list[Conference], ranked: list[dict]
) -> list[dict] | None:
    """The eight playoff teams in bracket order, from ``ranked`` (every
    team, best first, as StandingsRepository.ranked sorts them).

    Each league sends its division winners, best record first, then its
    best other teams as wild cards, four in all. They're placed so the first
    round and the semifinals stay inside each league (1 v 8 and 4 v 5 meet
    in one semifinal, 2 v 7 and 3 v 6 in the other) and the final is one
    league's champion against the other's. The league whose top team has the
    better record gets the 1 spot.

    None when the league has no divisions to seed by, or too few teams."""
    if len(conferences) != 2:
        return None
    place = {r["team_id"]: i for i, r in enumerate(ranked)}
    by_id = {r["team_id"]: r for r in ranked}
    per_league = []
    for conf in conferences:
        winners = []
        for div in conf.divisions:
            teams = [t for t in div.team_ids if t in place]
            if teams:
                winners.append(min(teams, key=place.get))
        winners.sort(key=place.get)
        rest = sorted(
            (t for t in conf.team_ids if t in place and t not in winners),
            key=place.get,
        )
        seeds = (winners + rest)[:PLAYOFF_TEAMS_PER_LEAGUE]
        if len(seeds) < PLAYOFF_TEAMS_PER_LEAGUE:
            return None
        per_league.append(seeds)
    per_league.sort(key=lambda seeds: place[seeds[0]])
    first, second = per_league
    # bracket spot -> (league, its seed)
    slots = {
        1: first[0],
        4: first[1],
        5: first[2],
        8: first[3],
        2: second[0],
        3: second[1],
        6: second[2],
        7: second[3],
    }
    return [by_id[slots[i]] for i in range(1, 9)]
