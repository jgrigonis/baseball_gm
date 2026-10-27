# src/api/routers/tutorial.py
#
# The new-user tutorial: the coach panel in a practice league, and the
# first-visit tips on each dashboard tab. Starting a practice league is in
# leagues.py with the rest of league creation.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from src.api.dependencies import DB, GM, User
from src.api.services.coach import coach_ctx
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.user_repo import UserRepository
from src.web.utils import templates

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/coach", response_class=HTMLResponse)
def coach_panel(request: Request, league_id: str, db: DB, gm: GM):
    """The coach panel, refreshed after each tab change or save. Empty
    outside a practice league."""
    coach = coach_ctx(db, LeagueRepository(db).get_by_id(league_id))
    if not coach:
        return HTMLResponse("")
    return templates.TemplateResponse(
        request,
        "dashboard/partials/_coach.html",
        {"coach": coach, "league_id": league_id},
    )


class TipRequest(BaseModel):
    tip: str


@router.post("/tips/dismiss")
def dismiss_tip(body: TipRequest, db: DB, user: User):
    UserRepository(db).dismiss_tip(user["id"], body.tip[:40])
    db.commit()
    return JSONResponse({"dismissed": body.tip})


@router.post("/tips/reset")
def reset_tips(db: DB, user: User):
    UserRepository(db).reset_tips(user["id"])
    db.commit()
    return JSONResponse({"reset": True})
