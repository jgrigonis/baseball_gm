# src/api/routers/roster.py
#
# Roster tab and saving the 40-man roster.

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.services import icons
from src.api.dependencies import DB, GM, ActiveLeague, IsHTMX, User
from src.api.schemas import RosterSaveRequest
from src.api.services import coach
from src.api.view_models.player_cards import (
    attach_moods,
    attach_injuries,
    attach_roster_stats,
    roster_card,
)
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.bullpen_roles_repo import BullpenRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.happiness_repo import HappinessRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.player.contracts import format_salary, minors_salary
from src.player.face import face_url
from src.team.roster_limits import MIN_PLAYING_ROSTER
from src.web.utils import _current_league_date, _shell_ctx, tab_response

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
        team = TeamRepository(db).get_city_and_mascot(team_id) or {}
        for row in player_repo.get_team_roster_with_skills(team_id):
            card = roster_card(row)
            card["jersey_number"] = row.get("jersey_number")
            card["face_url"] = face_url(
                card["player_id"], card.get("age"), team.get("city"), team.get("mascot")
            )
            players.append(card)

    # Unhappy players, trade requests and players sitting out
    # (src/player/happiness.py).
    attach_moods(db, league_id, players)
    icons.attach(db, team_id, players)

    # Season stats for display on roster cards
    season_id = ctx.get("season_id")
    if season_id and team_id:
        stats_map = PlayerSeasonStatsRepository(db).get_team_stats_map(
            season_id, team_id
        )
        attach_roster_stats(players, stats_map)

    inj = InjuryRepository(db, league_id)
    attach_injuries(
        players,
        inj.get_team_injuries(team_id),
        inj.get_team_injury_types(team_id),
        inj.get_rust([p["player_id"] for p in players]),
    )

    # Contracts: each player's salary this season, and the team's payroll.
    ctx["payroll_text"] = None
    contracts = ContractRepository(db)
    year = contracts.current_year(league_id)
    if team_id and year is not None:
        deals = contracts.active_for([p["player_id"] for p in players], year)
        farm_pay = format_salary(
            minors_salary(BudgetRepository(db).salary_scale(league_id, year))
        )
        for p in players:
            deal = deals.get(p["player_id"])
            p["salary"] = deal["salary"] if deal else None
            p["salary_text"] = format_salary(deal["salary"]) if deal else None
            p["rookie_deal"] = bool(deal and deal["kind"] == "rookie")
            # Off the payroll in the minors: paid the minor league salary
            # until he plays a game on the 40-man.
            p["farm_pay_text"] = farm_pay if deal and not deal["on_payroll"] else None
        ctx["payroll_text"] = format_salary(contracts.payroll(team_id, year))
        dead = contracts.dead_money(team_id, year)
        ctx["dead_money_text"] = format_salary(dead) if dead else None
        ctx["budget"] = BudgetRepository(db).standing(league_id, team_id, year)
    ctx["players"] = players
    return tab_response(request, htmx, "dashboard/partials/roster.html", ctx)


@router.get("/leagues/{league_id}/roster/trade-requests")
def roster_trade_requests(league_id: str, db: DB, gm: GM):
    """How many of the GM's players have asked to be traded: the Roster tab's
    badge, refreshed after each sim and trade."""
    return JSONResponse(
        {
            "count": HappinessRepository(db, league_id).team_trade_requests(
                gm.get("team_id")
            )
        }
    )


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
    GMRepository(db).mark_roster_saved(gm["id"])
    coach.mark(db, league_id, "roster")
    db.commit()
    return JSONResponse({"saved": len(forty_man_ids)})


@router.post("/leagues/{league_id}/roster/{player_id}/minors")
def send_to_minors(
    league_id: str,
    player_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    """Send one player off the 40-man to the minors (the Lineup tab's red −).

    Same rule as saving the Roster tab: the 40-man keeps at least 25. A
    starter leaves the rotation and a reliever loses his bullpen role, so
    the sim never hands the ball to a player in the minors.
    """
    team_id = gm["team_id"]
    player_repo = PlayerRepository(db)
    team_player_ids = player_repo.get_player_ids_from_team_players(team_id)
    if player_id not in team_player_ids:
        return JSONResponse({"detail": "He isn't on your team."}, status_code=422)

    status_repo = PlayerStatusRepository(db)
    forty = set(status_repo.get_by_team_and_status(team_id, "40man")) | set(
        status_repo.get_by_team_and_status(team_id, "26man")
    )
    if player_id not in forty:
        return JSONResponse({"detail": "He's already in the minors."}, status_code=422)
    minimum = min(MIN_PLAYING_ROSTER, len(team_player_ids))
    if len(forty) - 1 < minimum:
        return JSONResponse(
            {
                "detail": f"Your 40-man needs at least {MIN_PLAYING_ROSTER} players. "
                "Add someone on the Roster tab first."
            },
            status_code=422,
        )

    status_repo.set_status(player_id, "minors")

    season_id = SeasonRepository(db).get_most_recent_season_from_league(league_id)
    if season_id:
        league = LeagueRepository(db).get_by_id(league_id)
        effective_date = _current_league_date(
            db,
            season_id,
            league["state"] if league else "preseason",
            all_star_game=False,
        )
        TeamRotationsRepository(db, league_id).end_player(
            team_id, season_id, player_id, effective_date
        )
        BullpenRepository(db).close_active_role(
            team_id, player_id, season_id, effective_date or date.today().isoformat()
        )
    db.commit()
    return JSONResponse({"sent_down": player_id})
