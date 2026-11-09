# src/api/routers/seasons.py
#
# End-of-season pages: season summary and retirements.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GMOrViewer, IsHTMX, User
from src.db.repositories.gm_repo import GMRepository
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
    # Someone who took over a team after the playoffs lands here: this season
    # was their team's, not theirs, and their first is the one coming up.
    joined = (gm or {}).get("joined_year")
    ctx["new_gm_year"] = (
        joined
        if ctx.get("league_state") == "offseason"
        and ctx.get("summary_season_id") == ctx["season_id"]
        and joined
        and joined > (ctx.get("season_year") or joined)
        else None
    )
    # The GM has seen how the season ended: from here the next-move button
    # points on to Expiring Deals on every page (next_move.pick).
    if (
        ctx.get("league_state") == "offseason"
        and gm
        and gm.get("id")
        and not gm.get("is_viewer")
        and ctx.get("summary_season_id") == ctx["season_id"]
        and not ctx.get("summary_seen")
    ):
        GMRepository(db).mark_summary_seen(gm["id"], ctx["season_id"])
        db.commit()
    return tab_response(request, htmx, "dashboard/partials/season_summary.html", ctx)


@router.get("/leagues/{league_id}/retirement", response_class=HTMLResponse)
def retirement(
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
    ctx.update(retirement_context(db, league_id, my_team_id, season_id))
    return tab_response(request, htmx, "dashboard/partials/retirement.html", ctx)
