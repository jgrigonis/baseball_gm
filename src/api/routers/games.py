# src/api/routers/games.py
#
# Box score and play-by-play panel for one game.

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GMOrViewer, User
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.player_games import PlayerGameRepository
from src.stats import formulas
from src.web.utils import _shell_ctx, templates

log = logging.getLogger(__name__)

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/games/{game_id}/panel", response_class=HTMLResponse)
def game_panel(
    request: Request,
    league_id: str,
    game_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
):
    my_team_id = gm["team_id"]

    game_repo = GameRepository(db)
    pgs_repo = PlayerGameRepository(db)

    game = game_repo.get_with_teams(game_id)
    if not game:
        return HTMLResponse("Game not found", status_code=404)

    # Box score
    bat_rows = pgs_repo.get_batting_box_score(game_id)
    pit_rows = pgs_repo.get_pitching_box_score(game_id)

    fmt_ip = formulas.ip_str

    home_bat = [r for r in bat_rows if r["team_id"] == game["home_team_id"]]
    away_bat = [r for r in bat_rows if r["team_id"] == game["away_team_id"]]
    home_pit = [r for r in pit_rows if r["team_id"] == game["home_team_id"]]
    away_pit = [r for r in pit_rows if r["team_id"] == game["away_team_id"]]
    for p in home_pit + away_pit:
        p["IP"] = fmt_ip(p["outs"] or 0)

    # Event log
    events_out = []
    for ed in game_repo.get_events(game_id):
        if ed.get("detail"):
            try:
                ed["detail_parsed"] = json.loads(ed["detail"])
            except ValueError:
                log.warning(
                    "Unparseable detail on event %s of game %s",
                    ed.get("id"),
                    game_id,
                )
                ed["detail_parsed"] = None
        else:
            ed["detail_parsed"] = None
        events_out.append(ed)

    ctx = _shell_ctx(request, db, gm, league_id, user)
    ctx.update(
        {
            "game": game,
            "home_bat": home_bat,
            "away_bat": away_bat,
            "home_pit": home_pit,
            "away_pit": away_pit,
            "events": events_out,
            "my_team_id": my_team_id,
            "fmt_ip": fmt_ip,
        }
    )
    return templates.TemplateResponse(
        request=request, name="dashboard/partials/game_panel_content.html", context=ctx
    )
