# src/api/routers/ready.py
#
# The ready-check for multiplayer leagues: each GM marks themselves ready (or
# away), and the league sims its next period when everyone is ready or the
# Decision Window runs out. See src/api/services/ready_check.py.

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.api.dependencies import DB, GM, ActiveLeague
from src.api.services import ready_check, turn_alerts
from src.db.repositories.season_repo import SeasonRepository
from src.web.utils import _current_league_date

router = APIRouter(tags=["web"])


def _status(db, league_id: str, gm) -> JSONResponse:
    # The page polls this while it's showing: the GM is here, so no turn
    # email (src/api/services/turn_alerts.py).
    turn_alerts.mark_seen(db, gm["id"])
    ready_check.advance_if_due(db, league_id)
    body = ready_check.status(db, league_id, gm["id"])
    if body["multiplayer"]:
        # The top bar's date, so the page can move it on after a period.
        season_id = SeasonRepository(db).get_current_id_for_league(league_id)
        body["current_date"] = _current_league_date(db, season_id, body["league_state"])
    return JSONResponse(body)


@router.get("/leagues/{league_id}/sim/status")
def sim_status(league_id: str, db: DB, gm: GM):
    """Who's ready, who the league is waiting on, and the time left. Also runs
    the next period if it has come due, so clients poll this."""
    return _status(db, league_id, gm)


@router.post("/leagues/{league_id}/ready")
def mark_ready(league_id: str, db: DB, gm: GM, _active: ActiveLeague):
    ready_check.set_ready(db, league_id, gm["id"], True)
    return _status(db, league_id, gm)


@router.delete("/leagues/{league_id}/ready")
def unmark_ready(league_id: str, db: DB, gm: GM, _active: ActiveLeague):
    ready_check.set_ready(db, league_id, gm["id"], False)
    return _status(db, league_id, gm)


class AwayRequest(BaseModel):
    away: bool


@router.post("/leagues/{league_id}/away")
def mark_away(league_id: str, body: AwayRequest, db: DB, gm: GM, _active: ActiveLeague):
    ready_check.set_away(db, gm["id"], body.away)
    return _status(db, league_id, gm)
