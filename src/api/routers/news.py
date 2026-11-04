# src/api/routers/news.py
#
# The News tab: the league's news feed (src/api/services/news/). Its URL is
# /headlines because /leagues/{id}/news is the per-GM injury news the sim
# pages poll (routers/sim.py).

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.dependencies import DB, GM, GMOrViewer, IsHTMX, User
from src.api.view_models.news import news_context
from src.config import settings
from src.db.repositories.news_repo import NewsRepository
from src.web.utils import _shell_ctx, render, tab_response

router = APIRouter(tags=["web"])


def _mine_cookie(league_id: str) -> str:
    """Each league remembers its own All / My team choice on the News tab."""
    return f"news_mine_{league_id}"


@router.get("/leagues/{league_id}/headlines", response_class=HTMLResponse)
def news_tab(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
    season_id: str | None = None,
    mine: int | None = None,
    before: int | None = None,
):
    """``mine`` shows only stories about the GM's team; ``before`` (a story
    id) is the next page, older than that story. The All / My team choice
    is remembered per league in a cookie, so the live refresh after each
    sim day (which reloads the plain tab URL) keeps it."""
    my_team_id = None if gm.get("is_viewer") else gm.get("team_id")
    chosen = None if mine is None else bool(mine)
    wanted = (
        chosen
        if chosen is not None
        else request.cookies.get(_mine_cookie(league_id)) == "1"
    )
    ctx_news = news_context(
        db, league_id, my_team_id, season_id or None, wanted, before
    )
    if not gm.get("is_viewer") and gm.get("id"):
        NewsRepository(db).mark_seen(gm["id"], ctx_news["news_newest_id"])
        db.commit()
    if before:
        # "Show older": just the next page of stories.
        return render(
            "dashboard/partials/_news_page.html",
            {"league_id": league_id, **ctx_news},
        )
    ctx = _shell_ctx(request, db, gm, league_id, "headlines", user)
    ctx.update(ctx_news)
    ctx["news_unseen"] = 0
    # An earlier season's stories: no Play buttons.
    seasons = ctx_news["news_seasons"]
    ctx["news_past_season"] = bool(
        seasons and ctx_news["news_season_id"] != seasons[0]["id"]
    )
    resp = tab_response(request, htmx, "dashboard/partials/news.html", ctx)
    if chosen is not None:
        resp.set_cookie(
            _mine_cookie(league_id),
            "1" if chosen else "0",
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="lax",
            secure=settings.served_over_https,
        )
    return resp


@router.get("/leagues/{league_id}/headlines/unseen")
def news_unseen(league_id: str, db: DB, gm: GM):
    """How many stories the GM hasn't seen: the News tab's badge, refreshed
    after each sim."""
    return JSONResponse({"count": NewsRepository(db).count_unseen(league_id, gm["id"])})
