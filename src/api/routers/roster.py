# src/api/routers/roster.py
#
# Roster tab and saving the 40-man roster.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.dependencies import DB, GM, ActiveLeague, IsHTMX, User
from src.api.schemas import RosterSaveRequest
from src.api.services import coach
from src.api.view_models.player_cards import (
    attach_injuries,
    attach_roster_stats,
    roster_card,
)
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.team.roster_limits import MIN_PLAYING_ROSTER
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


# ── Tab: Roster ────────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/roster", response_class=HTMLResponse)
def roster(
    request: Request,
    htmx: IsHTMX,
    db: DB,
    user: User,
    gm: GM,
    league_id: str,
):
    ctx = _shell_ctx(request, db, gm, league_id, "roster", user)
    players = []
    team_id = gm["team_id"]

    if team_id:
        player_repo = PlayerRepository(db)
        for row in player_repo.get_team_roster_with_skills(team_id):
            players.append(roster_card(row))

    # Season stats for display on roster cards
    season_id = ctx.get("season_id")
    if season_id and team_id:
        stats_map = PlayerSeasonStatsRepository(db).get_team_stats_map(
            season_id, team_id
        )
        attach_roster_stats(players, stats_map)

    attach_injuries(players, InjuryRepository(db, league_id).get_team_injuries(team_id))
    ctx["players"] = players
    return tab_response(request, htmx, "dashboard/partials/roster.html", ctx)


@router.post("/leagues/{league_id}/roster/save", response_class=HTMLResponse)
def save_roster(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    """Save 40-man roster. Enforces the 40-player limit."""
    return HTMLResponse("ok")  # placeholder — real logic below


@router.put("/leagues/{league_id}/roster/save")
def save_roster_put(
    league_id: str,
    body: RosterSaveRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    """PUT endpoint for roster save from JS fetch. The 40-man holds 25 to 40."""
    team_id = gm["team_id"]
    forty_man_ids = body.forty_man

    if len(forty_man_ids) > 40:
        return JSONResponse(
            {
                "detail": f"40-man roster cannot exceed 40 players ({len(forty_man_ids)} submitted)"
            },
            status_code=422,
        )

    player_repo = PlayerRepository(db)
    status_repo = PlayerStatusRepository(db)
    team_player_ids = player_repo.get_player_ids_from_team_players(team_id)

    # A team that owns enough players has to keep 25 of them playing.
    minimum = min(MIN_PLAYING_ROSTER, len(team_player_ids))
    if len(forty_man_ids) < minimum:
        return JSONResponse(
            {
                "detail": f"40-man roster needs at least {MIN_PLAYING_ROSTER} players "
                f"({len(forty_man_ids)} submitted)"
            },
            status_code=422,
        )

    for pid in forty_man_ids:
        if pid not in team_player_ids:
            return JSONResponse(
                {"detail": f"Player {pid} not on this team"}, status_code=422
            )

    status_repo.set_40man_roster(team_player_ids, forty_man_ids)
    coach.mark(db, league_id, "roster")
    db.commit()
    return JSONResponse({"saved": len(forty_man_ids)})
