# src/api/routers/sim.py
#
# Advancing the league: simming regular-season days, playoff games, and
# running the offseason.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.api.dependencies import DB, GM, ActiveLeague, SinglePlayer
from src.api.schemas import SimRequest
from src.api.services.injury_news import take_injury_news
from src.api.services.offseason_service import run_offseason
from src.api.services.sim_next import sim_days
from src.api.services.sim_playoff import sim_playoff
from src.db.locks import league_lock
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.web.utils import _current_league_date

router = APIRouter(tags=["web"])


@router.post("/leagues/{league_id}/sim")
def sim_games(
    league_id: str,
    body: SimRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _: SinglePlayer,
):
    """Sim N games (or until season end). Returns JSON with results summary."""
    with league_lock(db, league_id):
        summary = sim_days(league_id, db, body.count)

    season_repo = SeasonRepository(db)
    league_repo = LeagueRepository(db)
    league = league_repo.get_by_id(league_id)
    league_state = league["state"] if league else "lobby"
    current_season_id = season_repo.get_current_id_for_league(league_id)
    current_date = _current_league_date(db, current_season_id, league_state)

    return JSONResponse(
        {
            **summary,
            "league_state": league_state,
            "current_date": current_date,
            **take_injury_news(db, gm["id"]),
        }
    )


@router.post("/leagues/{league_id}/playoffs/sim")
def sim_playoff_route(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _: SinglePlayer,
    mode: str = "game",
):
    with league_lock(db, league_id):
        result = sim_playoff(league_id, db, mode=mode)
    lr = LeagueRepository(db)
    result["league_state"] = lr.get_state(league_id)
    result.update(take_injury_news(db, gm["id"]))
    return JSONResponse(result)


@router.post("/leagues/{league_id}/offseason/begin")
def begin_offseason(
    league_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _: SinglePlayer,
):
    with league_lock(db, league_id):
        result = run_offseason(league_id, db)
    return JSONResponse({"ok": True, **result})


@router.get("/leagues/{league_id}/news")
def injury_news(league_id: str, db: DB, gm: GM):
    """The GM's injury news from sims they didn't see, e.g. ones another GM
    ran. Marked seen once returned."""
    return JSONResponse(take_injury_news(db, gm["id"]))
