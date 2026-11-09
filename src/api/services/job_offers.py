# src/api/services/job_offers.py
#
# Owners' job offers to a fired person (src/league/job_offers.py says how
# they're decided). A fired person in a re-entry league picks from these, not
# from every AI team (takeover.py).
#
# One set of offers per person per season they're out of work, made the
# first time they're asked for and kept, so the list doesn't shuffle while
# rosters change over the offseason. An offered team that a person has
# since taken over drops off; if none are left, the owners think again.

from __future__ import annotations

import random

from src.api.services import owner_review
from src.api.services import owners as owner_service
from src.league import job_offers as jo


def offers(
    conn, league_id: str, user_id: str, year: int, open_teams: list[dict]
) -> list[dict]:
    """The open teams (takeover.open_teams rows) whose owners offer this
    person a job for the season starting in `year`, each with the owner's
    name, archetype and message."""
    by_id = {t["team_id"]: t for t in open_teams}
    if not by_id:
        return []
    rows = _stored(conn, league_id, user_id, year)
    if not any(r["team_id"] in by_id for r in rows):
        _make(conn, league_id, user_id, year, list(by_id))
        rows = _stored(conn, league_id, user_id, year)
    owners_by_team = owner_service.ensure(conn, league_id)
    out = []
    for r in rows:
        team = by_id.get(r["team_id"])
        if not team:
            continue
        owner = owners_by_team.get(r["team_id"], {})
        out.append(
            team
            | {
                "message": r["message"],
                "owner_name": owner.get("name"),
                "owner_archetype": owner.get("archetype"),
            }
        )
    return sorted(out, key=lambda t: (t["city"], t["mascot"]))


def _stored(conn, league_id: str, user_id: str, year: int) -> list[dict]:
    return [
        dict(r)
        for r in conn.execute(
            """SELECT team_id, message FROM gm_job_offers
               WHERE league_id = %s AND user_id = %s AND year = %s""",
            (league_id, user_id, year),
        ).fetchall()
    ]


def reputation(conn, league_id: str, user_id: str, year: int) -> int:
    """How the league's owners see this person (src/league/job_offers.py)."""
    seasons = [
        jo.Record(
            score=float(r["score"] or 0),
            made_playoffs=bool(r["made_playoffs"]),
            champion=bool(r["won_championship"]),
        )
        for r in conn.execute(
            """SELECT e.score, e.made_playoffs, e.won_championship
               FROM gm_season_evaluations e JOIN gms g ON g.id = e.gm_id
               WHERE g.league_id = %s AND e.detail->>'who' = %s
                 AND e.score IS NOT NULL""",
            (league_id, user_id),
        ).fetchall()
    ]
    # A firing after the season of year Y is felt by the job for Y + 1.
    ago = [
        max(0, year - 1 - r["year"])
        for r in conn.execute(
            "SELECT year FROM gm_firings WHERE league_id = %s AND user_id = %s",
            (league_id, user_id),
        ).fetchall()
    ]
    return jo.reputation(seasons, ago)


def _ranks(conn, league_id: str) -> dict[str, dict]:
    """Each team's latest team-state ranks (0 best to 1 worst)."""
    rows = conn.execute(
        """SELECT DISTINCT ON (team_id) team_id, inputs FROM team_states
           WHERE league_id = %s ORDER BY team_id, id DESC""",
        (league_id,),
    ).fetchall()
    return {r["team_id"]: r["inputs"] or {} for r in rows}


def _make(conn, league_id: str, user_id: str, year: int, team_ids: list[str]):
    conn.execute(
        "DELETE FROM gm_job_offers WHERE league_id = %s AND user_id = %s AND year = %s",
        (league_id, user_id, year),
    )
    rep = reputation(conn, league_id, user_id, year)
    owners_by_team = owner_service.ensure(conn, league_id)
    security = owner_review.security_now(conn, league_id)
    ranks = _ranks(conn, league_id)
    teams = {
        r["id"]: dict(r)
        for r in conn.execute(
            "SELECT id, city, mascot FROM teams WHERE id = ANY(%s)", (team_ids,)
        ).fetchall()
    }
    jobs, appeal = [], {}
    for team_id in team_ids:
        owner = owners_by_team.get(team_id)
        if not owner or team_id not in teams:
            continue
        r = ranks.get(team_id, {})
        appeal[team_id] = jo.appeal(
            r.get("rank_now", 0.5),
            r.get("rank_future", 0.5),
            owner_service.market_of(teams[team_id]),
        )
        sec = security.get(team_id, {}).get("job_security")
        jobs.append(
            jo.Job(
                team_id,
                owner["archetype"],
                jo.bar(appeal[team_id], owner["traits"], sec),
            )
        )
    chosen, only = jo.choose(jobs, rep)
    for team_id in chosen:
        owner = owners_by_team[team_id]
        rng = random.Random(f"{league_id}:{user_id}:{year}:{team_id}")
        conn.execute(
            """INSERT INTO gm_job_offers
                   (league_id, user_id, year, team_id, owner_id, message)
               VALUES (%s, %s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING""",
            (
                league_id,
                user_id,
                year,
                team_id,
                owner["owner_id"],
                jo.message(owner["archetype"], rep, appeal[team_id], only, rng),
            ),
        )
