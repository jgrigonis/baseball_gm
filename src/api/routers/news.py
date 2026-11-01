# src/api/routers/news.py
#
# The News tab: the league's news feed (src/api/services/news/). Its URL is
# /headlines because /leagues/{id}/news is the per-GM injury news the sim
# pages poll (routers/sim.py).

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GMOrViewer, IsHTMX, User
from src.api.view_models.news import news_context
from src.db.repositories.news_repo import NewsRepository
from src.web.utils import _shell_ctx, render, tab_response

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/headlines", response_class=HTMLResponse)
def news_tab(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
    season_id: str | None = None,
    mine: int = 0,
    before: int | None = None,
):
    """``mine`` shows only stories about the GM's team; ``before`` (a story
    id) is the next page, older than that story."""
    my_team_id = None if gm.get("is_viewer") else gm.get("team_id")
    ctx_news = news_context(
        db, league_id, my_team_id, season_id or None, bool(mine), before
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
    return tab_response(request, htmx, "dashboard/partials/news.html", ctx)
