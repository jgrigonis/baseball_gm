# src/api/routers/depth.py
"""The depth chart (Josh, 2026-11-14): four cards at the top of the Lineup
tab and the Depth Chart tab's diamond, both from view_models/depth_chart.py."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GM, IsHTMX, User
from src.api.view_models.depth_chart import depth_chart
from src.db.repositories.season_repo import SeasonRepository
from src.web.utils import _shell_ctx, render, tab_response

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


@router.get("/leagues/{league_id}/depth/cards", response_class=HTMLResponse)
def depth_cards(league_id: str, db: DB, gm: GM):
    """The four cards for the top of the Lineup tab."""
    season_id = SeasonRepository(db).get_most_recent_season_from_league(league_id)
    return render(
        "dashboard/partials/_depth_cards.html",
        {
            "league_id": league_id,
            "depth": depth_chart(db, league_id, season_id, gm.get("team_id")),
        },
    )
