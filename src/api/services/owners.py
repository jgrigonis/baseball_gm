# src/api/services/owners.py
#
# Team owners in a league (src/league/owners.py): every team gets one, drawn
# from the site-wide library, the first time the league needs them: when it
# starts, or, for a league that was already running when owners came in, the
# first time anything asks. An owner stays with the team for the whole league;
# the GM can change under them.
#
# The draw is weighted by each owner's chance and tilted by the team's market
# size (big markets draw more Tycoons and Showmen, small ones more
# Penny-Pinchers and Long-Gamers), with no repeats in a league unless every
# pickable owner is already in it. Each owner also gets a rival, usually a
# division rival.
#
# An owner's first season (since_year) is the first one they judge: the
# current season if it hasn't started, else the next one. So an owner who
# arrives mid-season doesn't judge the GM on games played before they came.

from __future__ import annotations

import random

from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.owner_repo import OwnerRepository
from src.league import budget as bg
from src.league import divisions, owners, team_pool

FALLBACK_MARKET = 3


def _first_year(conn, league_id: str) -> int | None:
    """The first season a newly seated owner judges, or None if the league
    has no season yet."""
    row = conn.execute(
        """SELECT s.id, s.year,
                  EXISTS (SELECT 1 FROM games g
                          WHERE g.season_id = s.id AND g.completed = 1) AS played
           FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s AND NOT s.is_backstory
           ORDER BY s.year DESC LIMIT 1""",
        (league_id,),
    ).fetchone()
    if not row or row["year"] is None:
        return None
    return row["year"] + (1 if row["played"] else 0)


def _teams(conn, league_id: str) -> list[dict]:
    rows = conn.execute(
        """SELECT DISTINCT t.id, t.city, t.mascot
           FROM league_season_teams lst JOIN teams t ON t.id = lst.team_id
           WHERE lst.league_id = %s
           ORDER BY t.city, t.mascot, t.id""",
        (league_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _market(team: dict) -> int:
    pool = team_pool.get(team["city"], team["mascot"]) or team_pool.by_city(
        team["city"]
    )
    return pool.market if pool else FALLBACK_MARKET


def ensure(conn, league_id: str, rng: random.Random | None = None) -> dict[str, dict]:
    """Every team's owner in this league, by team id (OwnerRepository
    .in_league rows), drawing one for any team that has none yet. Empty
    while the league has no teams."""
    repo = OwnerRepository(conn)
    have = repo.in_league(league_id)
    teams = _teams(conn, league_id)
    missing = [t for t in teams if t["id"] not in have]
    if not missing:
        return have
    since = _first_year(conn, league_id)
    if since is None:
        return have
    rng = rng or random.Random(f"{league_id}-owners")
    pool = repo.pool()
    taken = {o["owner_id"] for o in have.values()}
    mates: dict[str, list[str]] = {}
    for conf in divisions.load(conn, league_id):
        for div in conf.divisions:
            for t in div.team_ids:
                mates[t] = div.team_ids
    all_ids = [t["id"] for t in teams]
    for team in missing:
        owner = owners.choose(pool, taken, _market(team), rng)
        if owner is None:
            break
        taken.add(owner["id"])
        rival = owners.choose_rival(team["id"], mates.get(team["id"], []), all_ids, rng)
        repo.seat(league_id, team["id"], owner["id"], rival, since)
    return repo.in_league(league_id)


def card(conn, league_id: str, team_id: str) -> dict | None:
    """What anyone can see of a team's owner: name, bio, archetype, what
    owners of that kind want, the rival if they're known for one, and
    their first season. None if the team has no owner (yet)."""
    row = ensure(conn, league_id).get(team_id)
    if not row:
        return None
    rival = None
    if (
        row["rival_team_id"]
        and owners.clean_weights(row["weights"])["rivalry"] >= owners.STRONG
    ):
        t = conn.execute(
            "SELECT city, mascot FROM teams WHERE id = %s", (row["rival_team_id"],)
        ).fetchone()
        if t:
            rival = f"{t['city']} {t['mascot']}"
    return {
        "name": row["name"],
        "bio": row["bio"],
        "archetype": row["archetype"],
        "wants": owners.wants(row["archetype"]),
        "rival": rival,
        "since_year": row["since_year"],
    }


def league_table(conn, league_id: str) -> list[dict]:
    """Every team's owner, for the league's list: team, owner name and
    archetype, by city."""
    by_team = ensure(conn, league_id)
    out = []
    for team in _teams(conn, league_id):
        row = by_team.get(team["id"])
        if not row:
            continue
        out.append(
            {
                "team_id": team["id"],
                "team": f"{team['city']} {team['mascot']}",
                "name": row["name"],
                "archetype": row["archetype"],
            }
        )
    return out


def archetype_guide() -> list[dict]:
    """Each starting archetype and what its owners want, for the help list."""
    return [{"name": a.name, "wants": a.wants} for a in owners.ARCHETYPES]


def pay_rooms(
    conn, league_id: str, season_id: str, team_ids: list[str] | None = None
) -> dict[str, int]:
    """How much more payroll each team's owner will stand for this season,
    by team id: the budget the owner set from the league's cap (it already
    holds their leash), minus payroll now. Can be negative. Empty without budgets. AI GMs keep to
    it in trades (src/league/trades/ai_evaluator.py); people only get a
    warning."""
    row = conn.execute(
        "SELECT year FROM seasons WHERE id = %s", (season_id,)
    ).fetchone()
    if not row:
        return {}
    year = row["year"]
    budgets = BudgetRepository(conn).for_league(league_id, year)
    if not budgets:
        return {}
    contracts = ContractRepository(conn)
    repo = BudgetRepository(conn)
    cap = repo.cap(league_id, year)
    levels = repo.league_levels(league_id, year)
    farms = repo.league_minor_leagues(league_id, year)
    # The budget pays the front office and the minor leagues too
    # (src/league/budget.py).
    return {
        t: b
        - contracts.payroll(t, year)
        - bg.front_office_cost(cap, levels.get(t, {}))
        - farms.get(t, 0)
        for t, b in budgets.items()
        if team_ids is None or t in team_ids
    }
