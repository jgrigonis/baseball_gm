# src/api/routers/players.py
#
# Player detail: the slide-in panel and the career page, each with an
# optional ?compare=<id> for side-by-side.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GM, User
from src.api.view_models.player_detail import (
    league_current_date,
    player_career_data,
    player_panel_data,
)
from src.web.utils import _shell_ctx, templates

router = APIRouter(tags=["web"])


@router.get(
    "/leagues/{league_id}/players/{player_id}/panel", response_class=HTMLResponse
)
def player_panel(
    request: Request,
    league_id: str,
    player_id: str,
    db: DB,
    user: User,
    gm: GM,
    compare: str | None = None,
):
    current_date = league_current_date(db, league_id)
    ctx = _shell_ctx(request, db, gm, league_id, user)
    ctx["player"] = player_panel_data(db, league_id, player_id, current_date)
    ctx["compare_player"] = (
        player_panel_data(db, league_id, compare, current_date) if compare else None
    )
    return templates.TemplateResponse(
        request, "dashboard/partials/player_panel.html", ctx
    )


@router.get(
    "/leagues/{league_id}/players/{player_id}/career", response_class=HTMLResponse
)
def player_career(
    request: Request,
    league_id: str,
    player_id: str,
    db: DB,
    user: User,
    gm: GM,
    compare: str | None = None,
):
    ctx = _shell_ctx(request, db, gm, league_id, user)
    ctx["player"] = player_career_data(db, league_id, player_id)
    ctx["compare_player"] = (
        player_career_data(db, league_id, compare) if compare else None
    )
    return templates.TemplateResponse(
        request, "dashboard/partials/player_career.html", ctx
    )
