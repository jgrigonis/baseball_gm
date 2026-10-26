# src/api/routers/leaders.py
#
# League leaders tab.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GMOrViewer, IsHTMX, User
from src.api.view_models.leaders import leaders_context
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/leaders", response_class=HTMLResponse)
def leaders(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
    category: str = "batting",
    season: str | None = None,
):
    ctx = _shell_ctx(request, db, gm, league_id, "leaders", user)
    my_team_id = gm["team_id"] if gm else None
    ctx.update(leaders_context(db, league_id, season, my_team_id))
    ctx["category"] = category
    return tab_response(request, htmx, "dashboard/partials/leaders.html", ctx)
