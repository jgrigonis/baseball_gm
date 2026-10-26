# src/api/routers/playoffs.py
#
# Playoffs tab.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GMOrViewer, IsHTMX, User
from src.api.view_models.playoffs import playoffs_context
from src.api.view_models.seasons import past_season
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/playoffs", response_class=HTMLResponse)
def playoffs(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
    season_id: str | None = None,
):
    """`season_id` (from a season summary) shows that season's bracket."""
    ctx = _shell_ctx(request, db, gm, league_id, "playoffs", user)
    past = past_season(db, league_id, season_id, ctx["season_id"])
    ctx.update(
        playoffs_context(
            db, league_id, past["id"] if past else ctx["season_id"], gm["team_id"]
        )
    )
    ctx["past_season"] = past
    return tab_response(request, htmx, "dashboard/partials/playoffs.html", ctx)
