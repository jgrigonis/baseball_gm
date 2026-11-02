# src/api/routers/standings.py
#
# Standings and schedule tabs.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GM, GMOrViewer, IsHTMX, User
from src.api.view_models.news import headlines
from src.api.view_models.schedule import schedule_context
from src.api.view_models.seasons import past_season
from src.api.view_models.standings import standings_context
from src.config import settings
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])

STANDINGS_VIEWS = ("divisions", "overall")


def _view_cookie(league_id: str) -> str:
    """Each league remembers its own Divisions / Overall choice."""
    return f"standings_view_{league_id}"


@router.get("/leagues/{league_id}/standings", response_class=HTMLResponse)
def standings(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
    season_id: str | None = None,
    view: str | None = None,
):
    """`season_id` (from the History tab) shows that season's final standings.
    `view` "overall" shows one table of every team instead of the divisions.
    The choice is remembered per league in a cookie, so the live refresh
    after each sim day (which reloads the plain tab URL) keeps it."""
    ctx = _shell_ctx(request, db, gm, league_id, "standings", user)
    my_team_id = gm["team_id"] if gm else None
    past = past_season(db, league_id, season_id, ctx["season_id"])
    ctx.update(
        standings_context(
            db,
            league_id,
            past["id"] if past else ctx["season_id"],
            my_team_id,
            past_season=bool(past),
        )
    )
    ctx["past_season"] = past
    if not past:
        ctx["headlines"] = headlines(
            db, league_id, None if ctx["is_viewer"] else my_team_id
        )
    chosen = view if view in STANDINGS_VIEWS else None
    wanted = chosen or request.cookies.get(_view_cookie(league_id))
    ctx["standings_view"] = (
        "overall" if wanted == "overall" or not ctx["groups"] else "divisions"
    )
    resp = tab_response(request, htmx, "dashboard/partials/standings.html", ctx)
    if chosen:
        resp.set_cookie(
            _view_cookie(league_id),
            chosen,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="lax",
            secure=settings.served_over_https,
        )
    return resp


@router.get("/leagues/{league_id}/schedule", response_class=HTMLResponse)
def schedule(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    ctx = _shell_ctx(request, db, gm, league_id, "schedule", user)
    my_team_id = gm["team_id"] if gm else None
    ctx.update(schedule_context(db, league_id, ctx["season_id"], my_team_id))
    return tab_response(request, htmx, "dashboard/partials/schedule.html", ctx)
