# src/api/routers/players.py
#
# Player detail: the slide-in panel and the career page. The panel takes up to
# two ?compare=<id> for side-by-side (three players at most), and ?give= /
# ?get= to tag players from a trade offer. The career page takes one compare.

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GMOrViewer, User
from src.api.view_models.player_detail import (
    league_current_date,
    player_career_data,
    player_panel_data,
)
from src.web.utils import _shell_ctx, templates

router = APIRouter(tags=["web"])

# The panel shows at most this many players side by side.
MAX_COMPARE = 3


@router.get(
    "/leagues/{league_id}/players/{player_id}/panel", response_class=HTMLResponse
)
def player_panel(
    request: Request,
    league_id: str,
    player_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
    compare: list[str] = Query(default=[]),
    give: list[str] = Query(default=[]),
    get: list[str] = Query(default=[]),
):
    current_date = league_current_date(db, league_id)
    ctx = _shell_ctx(request, db, gm, league_id, user=user)
    ctx["player"] = player_panel_data(db, league_id, player_id, current_date)
    # The first player, then the others in order, without repeats.
    ids = list(dict.fromkeys([player_id, *compare]))[:MAX_COMPARE]
    others = (player_panel_data(db, league_id, i, current_date) for i in ids[1:])
    ctx["compare_players"] = [p for p in others if p]
    ctx["max_compare"] = MAX_COMPARE
    # From a trade offer: which players you'd give and which you'd get.
    ctx["sides"] = {**{i: "give" for i in give}, **{i: "get" for i in get}}
    # Your own players can be released, and free agents signed.
    ctx["my_team_id"] = gm.get("team_id") if gm and not ctx.get("is_viewer") else None
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
    gm: GMOrViewer,
    compare: str | None = None,
):
    ctx = _shell_ctx(request, db, gm, league_id, user=user)
    ctx["player"] = player_career_data(db, league_id, player_id)
    ctx["compare_player"] = (
        player_career_data(db, league_id, compare) if compare else None
    )
    return templates.TemplateResponse(
        request, "dashboard/partials/player_career.html", ctx
    )
