# src/api/routers/stats.py
#
# Team stats tab.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GMOrViewer, IsHTMX, User
from src.api.view_models.team_stats import team_stats_context
from src.db.repositories.all_star_repo import AllStarRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/stats", response_class=HTMLResponse)
def stats(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
    team_id: str | None = None,
    season_id: str | None = None,
    postseason: int = 0,
):
    ctx = _shell_ctx(request, db, gm, league_id, "stats", user)
    my_team_id = gm["team_id"] if gm else None
    ctx.update(
        team_stats_context(
            db,
            league_id,
            ctx["season_id"],
            my_team_id,
            team_id,
            season_id,
            postseason,
        )
    )
    if ctx["selected_season_id"]:
        # Rookies and All-Stars of the season on show, which can be an earlier one.
        ctx["rookie_ids"] = PlayerSeasonStatsRepository(db).get_rookie_ids(
            league_id, ctx["selected_season_id"]
        )
        ctx["all_star_ids"] = AllStarRepository(db).ids(ctx["selected_season_id"])
    return tab_response(request, htmx, "dashboard/partials/stats.html", ctx)
