# src/league/real_seasons/__init__.py
"""
Real seasons: a league that starts with a real MLB season's players.

Each data file (data/YEAR.json) holds every club of that season with its 40
players by playing time, already rated on our 17 skills by
scripts/real_rosters.py from the Lahman Baseball Database. A player is rated
against his own league that season (era-relative), then given the skill a
generated player at the same percentile has, so real and generated players
share one scale. Stamina and recovery are the exception: those are rated
against 2015-2025 pitchers, since old-time workloads really were bigger.

The clubs play as the league's own teams (the team pool's names, uniforms,
markets): a club goes to a team in the same city when the league has one,
the rest by size, the biggest crowds to the biggest markets. Only the
rosters are real.
"""

from __future__ import annotations

import functools
import json
import random
import uuid
from pathlib import Path

from src.league import team_pool
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.team.team_record import TeamRecord

DATA_DIR = Path(__file__).parent / "data"

# Order of a player's "skills" list in the data files.
SKILLS = (
    "contact",
    "power",
    "eye",
    "speed",
    "base_running",
    "bunting",
    "durability",
    "clutch",
    "catching",
    "infield",
    "outfield",
    "arm",
    "accuracy",
    "strikes",
    "ground_balls",
    "stamina",
    "recovery",
)

# A real season is one MLB: 30 clubs (since 1998).
TEAMS = 30


def available() -> tuple[int, ...]:
    """Seasons a league can start from, newest first."""
    return tuple(sorted((int(p.stem) for p in DATA_DIR.glob("*.json")), reverse=True))


@functools.cache
def load(year: int) -> dict:
    path = DATA_DIR / f"{year}.json"
    if not path.exists():
        raise ValueError(f"No real season {year}.")
    return json.loads(path.read_text())


def assign_clubs(clubs: list[dict], teams: list[tuple[str, str]]) -> list[dict]:
    """The club each team plays with, in the order of `teams` ((city,
    mascot) pairs). Same city first, the bigger-drawing club when a city has
    two; the rest by size, biggest crowds to biggest markets."""
    if len(clubs) != len(teams):
        raise ValueError(f"{len(clubs)} clubs for {len(teams)} teams.")
    by_crowd = sorted(clubs, key=lambda c: -c["attendance"])
    out: dict[int, dict] = {}
    left = list(by_crowd)
    for i, (city, _) in enumerate(teams):
        same = [c for c in left if c["name"].startswith(city + " ")]
        if same:
            out[i] = same[0]
            left.remove(same[0])

    def market(i: int) -> int:
        pool = team_pool.get(*teams[i])
        return pool.market if pool else 0

    rest = sorted((i for i in range(len(teams)) if i not in out), key=market)
    rest.reverse()  # biggest market first
    for i, club in zip(rest, left):
        out[i] = club
    return [out[i] for i in range(len(teams))]


def player_record(p: dict, rng: random.Random) -> PlayerRecord:
    return PlayerRecord(
        id=uuid.UUID(int=rng.getrandbits(128)).hex,
        first_name=p["first"],
        last_name=p["last"],
        bats=p["bats"] if p["bats"] in ("L", "R", "S") else "R",
        throws=p["throws"] if p["throws"] in ("L", "R") else "R",
        position=p["pos"],
        skills=PlayerSkills(dict(zip(SKILLS, p["skills"])), age=p["age"]),
    )


def build_teams(
    year: int, teams: list[tuple[str, str]], rng: random.Random
) -> list[TeamRecord]:
    """The league's teams, (city, mascot), each with a real club's players."""
    clubs = assign_clubs(load(year)["clubs"], list(teams))
    return [
        TeamRecord(
            id=uuid.UUID(int=rng.getrandbits(128)).hex,
            city=city,
            mascot=mascot,
            players=tuple(player_record(p, rng) for p in club["players"]),
        )
        for (city, mascot), club in zip(teams, clubs)
    ]
