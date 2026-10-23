# src/api/routers/standings.py
#
# Standings and schedule tabs.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GM, IsHTMX, User
from src.api.view_models.schedule import schedule_context
from src.api.view_models.standings import standings_context
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/standings", response_class=HTMLResponse)
def standings(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    ctx = _shell_ctx(request, db, gm, league_id, "standings", user)
    my_team_id = gm["team_id"] if gm else None
    ctx.update(standings_context(db, league_id, ctx["season_id"], my_team_id))
    return tab_response(request, htmx, "dashboard/partials/standings.html", ctx)


@router.get("/leagues/{league_id}/schedule", response_class=HTMLResponse)
def schedule(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    ctx = _shell_ctx(request, db, gm, league_id, "schedule", user)
    my_team_id = gm["team_id"] if gm else None
    ctx.update(schedule_context(db, ctx["season_id"], my_team_id))
    return tab_response(request, htmx, "dashboard/partials/schedule.html", ctx)
