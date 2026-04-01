"""
src/web/routes/history.py
Season archive — past standings, stat leaders, GM evaluations
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/leagues/{league_id}/history")
templates = Jinja2Templates(directory="src/web/templates")


@router.get("/", response_class=HTMLResponse)
async def history_index(request: Request, league_id: str):
    """All completed seasons for this league."""
    # TODO: load completed seasons from DB
    return templates.TemplateResponse(
        "history/index.html",
        {
            "request": request,
            "league_id": league_id,
            "seasons": [],
        },
    )


@router.get("/{year}/", response_class=HTMLResponse)
async def history_season_summary_stub(request: Request, league_id: str, year: int):
    """
    Full summary for one season:
    - Final standings
    - GM verdict (retained / warned / fired)
    - Stat leaders
    - Playoff results
    - Win trend chart data
    """
    # TODO: load season summary from DB
    return templates.TemplateResponse(
        "history/season.html",
        {
            "request": request,
            "league_id": league_id,
            "year": year,
            "standings": [],
            "gm_evaluation": None,
            "stat_leaders": {},
            "playoff_bracket": None,
            "win_trend": [],  # list of {year, wins} for chart
        },
    )
