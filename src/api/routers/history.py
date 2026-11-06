# src/api/routers/history.py
#
# League history: the list of past seasons, the per-season page, and the
# Hall of Fame.

from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GM, GMOrViewer, IsHTMX, User
from src.api.services import hall_of_fame
from src.api.view_models.seasons import history_context
from src.league import hall_of_fame as hof_rules
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


@router.get("/leagues/{league_id}/hall-of-fame", response_class=HTMLResponse)
def hall_of_fame_page(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
    year: int | None = Query(None),
):
    """The Hall of Fame: a plaque for each inductee, and each year's ballot
    results (the latest, or ?year=)."""
    ctx = _shell_ctx(request, db, gm, league_id, user=user)
    my_team_id = gm["team_id"] if gm else None
    years = hall_of_fame.election_years(db, league_id)
    if year not in years:
        year = years[0] if years else None
    ctx.update(
        {
            "inductees": hall_of_fame.inductees(db, league_id, my_team_id),
            "election_years": years,
            "ballot_year": year,
            "ballot": hall_of_fame.ballot(db, league_id, year, my_team_id)
            if year
            else [],
            "elect_pct": int(hof_rules.ELECT_SHARE * 100),
            "keep_pct": int(hof_rules.KEEP_SHARE * 100),
            "first_year": _first_election_year(db, league_id),
        }
    )
    return tab_response(request, htmx, "dashboard/partials/hall_of_fame.html", ctx)


def _first_election_year(db, league_id: str) -> int | None:
    """The year of the league's first possible election: its first played
    season plus the five-year wait."""
    row = db.execute(
        """SELECT MIN(s.year) AS y FROM league_seasons ls
           JOIN seasons s ON s.id = ls.season_id
           WHERE ls.league_id = %s AND NOT s.is_backstory""",
        (league_id,),
    ).fetchone()
    return row["y"] + hof_rules.WAIT_SEASONS if row and row["y"] else None


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
