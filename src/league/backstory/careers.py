# src/league/backstory/careers.py
"""
Who played for which team in each past season.

Today's players are rewound to their younger selves (rewind.py). Going back
a year at a time from the newest past season:

- Going back, a player was in the majors the year before most of the time,
  less often the younger he was then, and never under 18. Once he's gone
  going back, he stays gone (that was before his debut).
- Mostly he was on the team he's on now, but each year back there's a
  chance he came over from another team, so careers move around a bit.
- Teams short of players in a past season get veterans who have since
  retired. Each is made like any player (born at 17 and aged up), retires
  after the season he was needed in, and plays the seasons before it too,
  so retirees have real careers.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from src.league.backstory.rewind import rewind
from src.player.player_factory import PlayerFactory
from src.player.positions import is_pitcher
from src.player.talent_caps import generate_talent_caps

# Chance a player was with the same team the year before.
STAY_CHANCE = 0.88
# Chance a player who was in the majors at some age was also there the
# year before, at each age (older: CAREER_CHANCE). League rosters carry a
# few 18-20 year olds, so players can debut that young.
DEBUT_CHANCE = {18: 0.3, 19: 0.45, 20: 0.6, 21: 0.75, 22: 0.85}
CAREER_CHANCE = 0.97
FIRST_MAJORS_AGE = 18
# The hitters and pitchers a past team needs (the engine's busiest 12 of
# each play nearly all the innings), and the minimums at catcher and
# starting pitcher. Teams short of these get retired veterans.
HITTERS = 12
PITCHERS = 12
MIN_CATCHERS = 1
MIN_STARTERS = 5
# A retiree's age in his last season.
RETIRE_AGES = (31, 38)
FIELD_POSITIONS = ("c", "1b", "2b", "3b", "ss", "lf", "cf", "rf")


@dataclass
class Career:
    """A player's past: his team and skills in each past season he played."""

    player_id: str
    first_name: str
    last_name: str
    bats: str
    throws: str
    position: str
    age_now: int  # current players: today; retirees: in their last season
    team_by_year: dict[int, str] = field(default_factory=dict)
    skills_by_year: dict[int, dict[str, float]] = field(default_factory=dict)
    retired_after: int | None = None  # retirees: the last season they played
    final_skills: dict[str, float] | None = None  # retirees: at retirement
    final_team_id: str | None = None

    def age_in(self, year: int, base_year: int) -> int:
        """His age in a past season. base_year is the league's first season
        for current players (age_now is then), and the last season played
        for retirees."""
        ref = self.retired_after if self.retired_after is not None else base_year
        return self.age_now - (ref - year)


def _plays_at(age: int, rng: random.Random) -> bool:
    if age < FIRST_MAJORS_AGE:
        return False
    return rng.random() < DEBUT_CHANCE.get(age, CAREER_CHANCE)


def _path(
    team_now: str,
    years: list[int],
    ages: list[int],
    teams: list[str],
    rng: random.Random,
) -> dict[int, str]:
    """His team in each of `years` (newest first) until his debut."""
    out = {}
    team = team_now
    for year, age in zip(years, ages):
        if not _plays_at(age, rng):
            break
        if rng.random() > STAY_CHANCE and len(teams) > 1:
            team = rng.choice([t for t in teams if t != team])
        out[year] = team
    return out


def current_careers(
    players: list[dict],
    base_year: int,
    years: int,
    teams: list[str],
    rng: random.Random,
) -> list[Career]:
    """Careers for today's players. players: dicts with id, first_name,
    last_name, bats, throws, position, age, team_id, skills (dict) and caps
    (dict or None)."""
    past = list(range(base_year - 1, base_year - years - 1, -1))
    out = []
    for p in players:
        ages = [p["age"] - (base_year - y) for y in past]
        path = _path(p["team_id"], past, ages, teams, rng)
        c = Career(
            player_id=p["id"],
            first_name=p["first_name"],
            last_name=p["last_name"],
            bats=p["bats"],
            throws=p["throws"],
            position=p["position"],
            age_now=p["age"],
            team_by_year=path,
        )
        if path:
            back = rewind(p["skills"], p["age"], len(path), p.get("caps"), rng)
            for k, year in enumerate(past[: len(path)]):
                c.skills_by_year[year] = back[k]
        out.append(c)
    return out


def _needs(roster: list[Career]) -> list[str]:
    """The positions a past team is short of, most needed first."""
    pitchers = [c for c in roster if is_pitcher(c.position)]
    hitters = [c for c in roster if not is_pitcher(c.position)]
    need = []
    catchers = sum(1 for c in hitters if c.position == "c")
    need += ["c"] * max(0, MIN_CATCHERS - catchers)
    starters = sum(1 for c in pitchers if c.position == "sp")
    need += ["sp"] * max(0, MIN_STARTERS - starters)
    short_h = HITTERS - len(hitters) - need.count("c")
    short_p = PITCHERS - len(pitchers) - need.count("sp")
    covered = {c.position for c in hitters} | set(need)
    open_spots = [p for p in FIELD_POSITIONS if p not in covered]
    for i in range(max(0, short_h)):
        need.append(open_spots[i] if i < len(open_spots) else None)
    need += ["rp"] * max(0, short_p)
    return need


def add_retirees(
    careers: list[Career],
    base_year: int,
    years: int,
    teams: list[str],
    rng: random.Random,
) -> list[Career]:
    """Fill every past team's roster with veterans who have since retired.
    Returns the retirees (also appended to careers)."""
    past = list(range(base_year - 1, base_year - years - 1, -1))
    oldest = past[-1]
    factory = PlayerFactory(rng=rng)
    retirees = []
    for year in past:
        for team in teams:
            roster = [c for c in careers if c.team_by_year.get(year) == team]
            for pos in _needs(roster):
                r = _make_retiree(factory, pos, year, oldest, team, teams, rng)
                careers.append(r)
                retirees.append(r)
    return retirees


def _make_retiree(factory, position, last_year, oldest, team, teams, rng) -> Career:
    if position is None:
        position = rng.choice(FIELD_POSITIONS)
    rec = factory.create(position=position)
    caps = generate_talent_caps(rec.skills.as_dict(), rng=rng)
    age_last = rng.randint(*RETIRE_AGES)
    final = rec.skills.age_to(age_last, rng=rng, caps=caps)
    final_skills = {k: float(v) for k, v in final.as_dict().items()}
    c = Career(
        player_id=rec.id,
        first_name=rec.first_name,
        last_name=rec.last_name,
        bats=rec.bats,
        throws=rec.throws,
        position=rec.position,
        age_now=age_last,
        retired_after=last_year,
        final_skills=final_skills,
        final_team_id=team,
    )
    # His last season, then the ones before it back to the oldest past
    # season (or his debut): the same team mostly, as for anyone.
    c.team_by_year[last_year] = team
    c.skills_by_year[last_year] = final_skills
    earlier = list(range(last_year - 1, oldest - 1, -1))
    if earlier:
        ages = [age_last - (last_year - y) for y in earlier]
        path = _path(team, earlier, ages, teams, rng)
        c.team_by_year.update(path)
        back = rewind(final_skills, age_last, len(path), caps, rng)
        for k, year in enumerate(earlier[: len(path)]):
            c.skills_by_year[year] = back[k]
    return c
