# src/api/routers/games.py
#
# Box score and play-by-play panel for one game.

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GMOrViewer, User
from src.api.view_models.box_score import (
    batting_order,
    in_order,
    pitching_order,
    used_batting_columns,
)
from src.api.view_models.line_score import headline, line_score
from src.api.view_models import play_by_play
from src.api.view_models.standouts import standouts
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.player_games import PlayerGameRepository
from src.db.repositories.all_star_repo import AllStarRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
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

    # Event log: also gives the box score its batting and pitching order
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
        # Debug notes like "fatigue=tired" are for admins only
        if not user.get("is_admin"):
            ed["reason"] = play_by_play.strip_debug(ed.get("reason"))
        events_out.append(ed)

    # Play-by-play: kept for the league's current season only
    plays = game_repo.get_plays(game_id)
    pbp = play_by_play.build(plays, events_out, game) if plays else None

    def _team_rows(rows: list[dict], team_id: str, order) -> list[dict]:
        mine = [r for r in rows if r["team_id"] == team_id]
        return in_order(mine, order(events_out, team_id))

    home_bat = _team_rows(bat_rows, game["home_team_id"], batting_order)
    away_bat = _team_rows(bat_rows, game["away_team_id"], batting_order)
    home_pit = _team_rows(pit_rows, game["home_team_id"], pitching_order)
    away_pit = _team_rows(pit_rows, game["away_team_id"], pitching_order)
    for p in home_pit + away_pit:
        p["IP"] = fmt_ip(p["outs"] or 0)

    # A staff that held the other side hitless over nine or more innings
    no_hitters = []
    for pit, team in ((away_pit, "away"), (home_pit, "home")):
        outs = sum(p["outs"] or 0 for p in pit)
        if pit and outs >= 27 and not any(p["H"] for p in pit):
            no_hitters.append(
                {
                    "team": f"{game[team + '_city']} {game[team + '_mascot']}",
                    "pitchers": ", ".join(
                        f"{p['first_name'][0]}. {p['last_name']}" for p in pit
                    ),
                    "combined": len(pit) > 1,
                }
            )

    # Scoreboard: runs by inning, R/H/E, a headline, the game's standout
    # performances and the decisions
    scoreboard = None
    if game["completed"] and game["home_score"] is not None:
        hits: dict[str, int] = {}
        for r in bat_rows:
            hits[r["team_id"]] = hits.get(r["team_id"], 0) + (r["H"] or 0)
        errors = pgs_repo.get_team_errors(game_id)
        stars = standouts(bat_rows, pit_rows, errors)
        scoreboard = line_score(game, hits, errors)
        scoreboard["headline"] = headline(game, bat_rows, pit_rows, no_hitters, stars)
        scoreboard["standouts"] = stars
        scoreboard["decisions"] = [
            (label, f"{p['first_name'][0]}. {p['last_name']}")
            for label, key in (("Win", "W"), ("Loss", "L"), ("Save", "SV"))
            for p in pit_rows
            if p[key]
        ]

    ctx = _shell_ctx(request, db, gm, league_id, user=user)
    ctx.update(
        {
            "game": game,
            "home_bat": home_bat,
            "away_bat": away_bat,
            # Shared by both teams so their tables line up
            "bat_cols": used_batting_columns(home_bat + away_bat),
            "home_pit": home_pit,
            "away_pit": away_pit,
            "no_hitters": no_hitters,
            "scoreboard": scoreboard,
            # Box score rows to highlight: (kind, player_id) -> feats
            "standout_rows": {
                (s["kind"], s["player_id"]): " · ".join(s["feats"])
                for s in (scoreboard or {}).get("standouts", [])
            },
            "events": events_out,
            "pbp": pbp,
            "my_team_id": my_team_id,
            "fmt_ip": fmt_ip,
            # Rookies and All-Stars of the season the game was played in.
            "rookie_ids": PlayerSeasonStatsRepository(db).get_rookie_ids(
                league_id, game["season_id"]
            ),
            "all_star_ids": AllStarRepository(db).ids(game["season_id"]),
        }
    )
    return templates.TemplateResponse(
        request=request, name="dashboard/partials/game_panel_content.html", context=ctx
    )
