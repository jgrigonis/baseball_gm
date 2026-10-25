# src/api/routers/playoffs.py
#
# Playoffs tab.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GM, IsHTMX, User
from src.api.view_models.playoffs import playoffs_context
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/playoffs", response_class=HTMLResponse)
def playoffs(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    ctx = _shell_ctx(request, db, gm, league_id, "playoffs", user)
    ctx.update(playoffs_context(db, league_id, ctx["season_id"], gm["team_id"]))
    return tab_response(request, htmx, "dashboard/partials/playoffs.html", ctx)
