# src/api/routers/standings.py
#
# Standings and schedule tabs.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GM, GMOrViewer, IsHTMX, User
from src.api.view_models.schedule import schedule_context
from src.api.view_models.seasons import past_season
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
    gm: GMOrViewer,
    season_id: str | None = None,
    view: str | None = None,
):
    """`season_id` (from the History tab) shows that season's final standings.
    `view` "overall" shows one table of every team instead of the divisions."""
    ctx = _shell_ctx(request, db, gm, league_id, "standings", user)
    my_team_id = gm["team_id"] if gm else None
    past = past_season(db, league_id, season_id, ctx["season_id"])
    ctx.update(
        standings_context(
            db,
            league_id,
            past["id"] if past else ctx["season_id"],
            my_team_id,
            past_season=bool(past),
        )
    )
    ctx["past_season"] = past
    ctx["standings_view"] = (
        "overall" if view == "overall" or not ctx["groups"] else "divisions"
    )
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
