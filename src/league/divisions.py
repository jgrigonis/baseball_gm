# src/league/divisions.py
"""
Leagues and divisions. Every league is split into two leagues, each split
into divisions of the same size:

- The 30-team World League has a fixed lineup, by geography (WORLD_LINEUP):
  the Atlantic and Pacific Leagues, three divisions of five each.
- Every other size (16, 20, 24, 28 or 32 teams) draws its teams into two
  leagues of two divisions at random when the league starts.

Standings group teams by division, the playoffs take each league's division
winners plus wild cards, and the weighted schedule setting plays division
rivals more often (src/league/weighted_schedule.py).

The split is kept in team_divisions, one row per team. Leagues started
before divisions existed have no rows, and everything falls back to one
table of all the teams.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# The team counts a league can be made with.
TEAM_COUNTS = (16, 20, 24, 28, 30, 32)
DEFAULT_TEAM_COUNT = 30

# conference -> division -> cities, in order.
WORLD_LINEUP: dict[str, dict[str, list[str]]] = {
    "Atlantic League": {
        "Americas": ["New York", "Chicago", "Toronto", "São Paulo", "Buenos Aires"],
        "South": ["Lisbon", "Madrid", "Paris", "Milan", "Vienna"],
        "North": ["London", "Dublin", "Amsterdam", "Frankfurt", "Warsaw"],
    },
    "Pacific League": {
        "Pacific Rim": [
            "Los Angeles",
            "San Francisco",
            "Mexico City",
            "Sydney",
            "Tokyo",
        ],
        "East Asia": ["Beijing", "Shanghai", "Hong Kong", "Seoul", "Singapore"],
        "Silk Road": ["Istanbul", "Dubai", "Mumbai", "Bangkok", "Jakarta"],
    },
}

# Names for a random draw: (league, its divisions).
DRAW_NAMES = [
    ("Founders League", ["Red", "Gold"]),
    ("Frontier League", ["Blue", "Green"]),
]

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


def world_cities() -> set[str]:
    return {c for divs in WORLD_LINEUP.values() for cs in divs.values() for c in cs}


def draw(teams: list[tuple[str, str]], rng: random.Random) -> list[Conference]:
    """Split the teams, as (team id, city), into leagues and divisions: the
    World League lineup when the teams are exactly its cities, otherwise a
    random draw into two leagues of two divisions. Empty, so no divisions,
    when the teams don't split into four even divisions (a test league)."""
    by_city = {city: tid for tid, city in teams}
    if len(by_city) == len(teams) and set(by_city) == world_cities():
        return [
            Conference(
                name,
                [
                    Division(d, [by_city[c] for c in cities])
                    for d, cities in divs.items()
                ],
            )
            for name, divs in WORLD_LINEUP.items()
        ]
    if not teams or len(teams) % 4:
        return []
    ids = [tid for tid, _ in teams]
    rng.shuffle(ids)
    size = len(ids) // 4
    out = []
    for c, (name, div_names) in enumerate(DRAW_NAMES):
        divisions = []
        for d, div_name in enumerate(div_names):
            start = (c * 2 + d) * size
            divisions.append(Division(div_name, ids[start : start + size]))
        out.append(Conference(name, divisions))
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
