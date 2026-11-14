# src/api/routers/depth.py
"""The Depth Chart tab (Josh, 2026-11-14): the diamond, rotation, bullpen and
batting order from view_models/depth_chart.py. It follows the team's saved
lineup, rotation and bullpen roles, so it matches the Lineup tab."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GM, IsHTMX, User
from src.api.view_models.depth_chart import depth_chart
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/depth", response_class=HTMLResponse)
def depth_tab(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
    team_id: str | None = None,
):
    """``team_id`` shows another team's chart (handy when shopping)."""
    ctx = _shell_ctx(request, db, gm, league_id, "depth", user)
    ctx["depth"] = depth_chart(
        db, league_id, ctx["season_id"], team_id or gm.get("team_id")
    )
    return tab_response(request, htmx, "dashboard/partials/depth_chart.html", ctx)
