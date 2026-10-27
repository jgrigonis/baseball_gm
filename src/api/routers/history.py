# src/api/routers/history.py
#
# League history: the list of past seasons, and the per-season page.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GM, GMOrViewer, IsHTMX, User
from src.api.view_models.seasons import history_context
from src.db.repositories.gm_evaluation_repo import GMEvaluationRepository
from src.db.repositories.season_repo import SeasonRepository
from src.web.utils import _shell_ctx, tab_response, templates

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/history", response_class=HTMLResponse)
def history(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
):
    ctx = _shell_ctx(request, db, gm, league_id, user=user)
    my_team_id = gm["team_id"] if gm else None
    ctx.update(history_context(db, league_id, my_team_id))
    return tab_response(request, htmx, "dashboard/partials/history.html", ctx)


@router.get("/leagues/{league_id}/history/{year}/", response_class=HTMLResponse)
def history_season_detail(
    request: Request,
    league_id: str,
    year: int,
    db: DB,
    gm: GM,
):
    season = SeasonRepository(db).get_by_league_and_year(league_id, year)
    evaluation = (
        GMEvaluationRepository(db).get(gm["id"], season["id"]) if season else None
    )

    return templates.TemplateResponse(
        request,
        "history/season.html",
        {
            "league_id": league_id,
            "year": year,
            "season": season,
            "gm_evaluation": evaluation,
            "standings": [],
            "stat_leaders": {},
            "win_trend": [],
        },
    )
