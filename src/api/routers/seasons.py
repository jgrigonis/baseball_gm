# src/api/routers/seasons.py
#
# End-of-season pages: season summary and retirements.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GMOrViewer, IsHTMX, User
from src.api.view_models.seasons import retirement_context, season_summary_context
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/season-summary", response_class=HTMLResponse)
def season_summary(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
    season_id: str | None = None,
):
    ctx = _shell_ctx(request, db, gm, league_id, user=user)
    my_team_id = gm["team_id"] if gm else None
    ctx.update(
        season_summary_context(db, league_id, season_id, ctx["season_id"], my_team_id)
    )
    ctx["my_team_name"] = ctx.get("team_name", "")
    return tab_response(request, htmx, "dashboard/partials/season_summary.html", ctx)


@router.get("/leagues/{league_id}/retirement", response_class=HTMLResponse)
def retirement(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
):
    ctx = _shell_ctx(request, db, gm, league_id, user)
    my_team_id = gm["team_id"] if gm else None
    ctx.update(retirement_context(db, league_id, my_team_id))
    return tab_response(request, htmx, "dashboard/partials/retirement.html", ctx)
