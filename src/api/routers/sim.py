# src/api/routers/sim.py
#
# Advancing the league: simming regular-season days, playoff games, and
# running the offseason.

from __future__ import annotations

import threading

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.api.dependencies import DB, GM
from src.api.schemas import SimRequest
from src.api.services.offseason_service import run_offseason
from src.api.services.sim_next import sim_next_day
from src.api.services.sim_playoff import sim_playoff
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.web.utils import _current_league_date

router = APIRouter(tags=["web"])

# sim_games runs in the thread pool, so two sims of one league (a second tab,
# or Sim clicked again after a reload) could otherwise play the same day
# twice. One lock per league queues them instead. Only covers one process.
_sim_locks: dict[str, threading.Lock] = {}


def _sim_lock(league_id: str) -> threading.Lock:
    return _sim_locks.setdefault(league_id, threading.Lock())


def _games_remaining(db, season_id: str | None) -> int:
    """Return the number of unplayed games remaining in a season."""
    return GameRepository(db).games_remaining(season_id)


@router.post("/leagues/{league_id}/sim")
def sim_games(
    league_id: str,
    body: SimRequest,
    db: DB,
    gm: GM,
):
    """Sim N games (or until season end). Returns JSON with results summary."""
    with _sim_lock(league_id):
        count = body.count

        season_repo = SeasonRepository(db)
        league_repo = LeagueRepository(db)

        results = []
        days_simmed = 0
        all_new_injuries = []
        all_returned = []
        remaining = _games_remaining(
            db, season_repo.get_current_id_for_league(league_id)
        )

        limit = remaining if count == "season" else min(int(count), remaining)

        for _ in range(limit):
            day_result = sim_next_day(league_id, db)
            gp = day_result.get("games_played", 0)
            if gp > 0:
                results.append(day_result)
                days_simmed += 1
                all_new_injuries.extend(day_result.get("new_injuries", []))
                all_returned.extend(day_result.get("returned", []))
            # Stop if season ended (no game_date) or if state changed out of season
            if not day_result.get("game_date"):
                break
            # Stop if no games played and it wasn't a transient error
            if gp == 0 and not day_result.get("errors"):
                break

        games_played = sum(r.get("games_played", 0) for r in results)
        new_remaining = _games_remaining(
            db, season_repo.get_current_id_for_league(league_id)
        )
        # If season just ended, trigger the state transition (playoffs setup)
        if new_remaining == 0 and days_simmed > 0:
            sim_next_day(league_id, db)

    league = league_repo.get_by_id(league_id)
    league_state = league["state"] if league else "lobby"
    current_season_id = season_repo.get_current_id_for_league(league_id)
    current_date = _current_league_date(db, current_season_id, league_state)

    return JSONResponse(
        {
            "days_simmed": days_simmed,
            "games_played": games_played,
            "games_remaining": new_remaining,
            "last_date": results[-1]["game_date"] if results else None,
            "league_state": league_state,
            "current_date": current_date,
            "new_injuries": all_new_injuries,
            "returned": all_returned,
        }
    )


@router.post("/leagues/{league_id}/playoffs/sim")
def sim_playoff_route(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
    mode: str = "game",
):
    result = sim_playoff(league_id, db, mode=mode)
    lr = LeagueRepository(db)
    result["league_state"] = lr.get_state(league_id)
    return JSONResponse(result)


@router.post("/leagues/{league_id}/offseason/begin")
def begin_offseason(
    league_id: str,
    db: DB,
    gm: GM,
):
    result = run_offseason(league_id, db)
    return JSONResponse({"ok": True, **result})
