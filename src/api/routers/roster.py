# src/api/routers/roster.py
#
# Roster tab and saving the 40-man roster.

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.services import arrivals
from src.api.services import icons
from src.api.dependencies import DB, GM, ActiveLeague, IsHTMX, User
from src.api.schemas import InjuredListRequest, RosterSaveRequest
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
from src.league.league_modes import is_blitz_style
from src.player.positions import is_pitcher
from src.team.injured_list import InjuredList, kinds_for, league_today
from src.team.roster_limits import MIN_PLAYING_ROSTER, league_active_limits
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
    arrivals.attach(db, league_id, team_id, players)

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
    # Speed Blitz has no salaries to show (Josh, 2026-11-14).
    if team_id and year is not None and ctx.get("has_money", True):
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
    # Long Form: the active (26-man) roster is picked here too, inside the
    # limits on the next game day (28 and 14 pitchers from September 1).
    league = LeagueRepository(db).get_by_id(league_id)
    ctx["long_form"] = bool(league) and not is_blitz_style(league.get("mode"))
    if ctx["long_form"]:
        _attach_il(db, league_id, team_id, players)
        ctx["il_today"] = league_today(db, league_id)
        limits = league_active_limits(db, dict(league))
        ctx["active_limits"] = {
            "max": limits.max_active,
            "min": limits.min_active,
            "pitchers": limits.max_pitchers,
            "expanded": limits.expanded,
        }
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

    league = LeagueRepository(db).get_by_id(league_id)
    long_form = bool(league) and not is_blitz_style(league.get("mode"))
    # Long Form: the 60-day injured list doesn't count toward the 40.
    sixty = InjuredList(db, league_id).sixty_ids(team_id) if long_form else set()
    if len(set(forty_man_ids) - sixty) > 40:
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

    if long_form:
        problem = _active_problem(db, dict(league), team_id, forty_man_ids, body.active)
        if problem:
            return JSONResponse({"detail": problem}, status_code=422)
        status_repo.set_40man_roster(team_player_ids, forty_man_ids)
        status_repo.bulk_set({pid: "26man" for pid in body.active})
    else:
        status_repo.set_40man_roster(team_player_ids, forty_man_ids)
    gms = GMRepository(db)
    gms.mark_roster_saved(gm["id"])
    gms.mark_preseason_saved(league_id, gm["id"], "roster")
    coach.mark(db, league_id, "roster")
    db.commit()
    return JSONResponse({"saved": len(forty_man_ids)})


def _active_problem(
    db, league: dict, team_id: str, forty_man_ids: list[str], active: list[str] | None
) -> str | None:
    """Why a Long Form active roster can't be saved, or None if it can."""
    limits = league_active_limits(db, league)
    active = active or []
    if len(set(active)) != len(active):
        return "A player is on the active roster twice."
    il = InjuredList(db, league["id"]).for_team(team_id)
    if set(active) & set(il):
        return "Players on the injured list can't be on the active roster."
    if not set(il) <= set(forty_man_ids):
        return "Players on the injured list stay on the 40-man."
    if not set(active) <= set(forty_man_ids):
        return "Only players on the 40-man can be on the active roster."
    if len(active) > limits.max_active:
        return f"The active roster holds at most {limits.max_active} ({len(active)} picked)."
    if len(active) < min(limits.min_active, len(forty_man_ids)):
        return (
            f"The active roster needs at least {limits.min_active} players "
            f"({len(active)} picked)."
        )
    rows = db.execute(
        "SELECT position FROM players WHERE id = ANY(%s)", (list(active),)
    ).fetchall()
    pitchers = sum(1 for r in rows if is_pitcher((r["position"] or "").lower()))
    if pitchers > limits.max_pitchers:
        return (
            f"The active roster holds at most {limits.max_pitchers} pitchers "
            f"({pitchers} picked)."
        )
    return None


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
    _leave_staff(db, league_id, team_id, player_id)
    db.commit()
    return JSONResponse({"sent_down": player_id})


@router.post("/leagues/{league_id}/roster/{player_id}/reserve")
def send_to_reserve(
    league_id: str,
    player_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    """Long Form: take one player off the active roster; he stays on the
    40-man (the Lineup tab's red −). The active roster keeps its minimum,
    and he leaves the rotation and bullpen like a player sent down."""
    team_id = gm["team_id"]
    status_repo = PlayerStatusRepository(db)
    active = status_repo.get_by_team_and_status(team_id, "26man")
    if player_id not in active:
        return JSONResponse(
            {"detail": "He isn't on your active roster."}, status_code=422
        )
    league = LeagueRepository(db).get_by_id(league_id)
    limits = league_active_limits(db, dict(league))
    if len(active) - 1 < limits.min_active:
        return JSONResponse(
            {
                "detail": f"Your active roster needs at least {limits.min_active} "
                "players. Call someone up on the Roster tab first."
            },
            status_code=422,
        )
    status_repo.set_status(player_id, "40man")
    _leave_staff(db, league_id, team_id, player_id)
    db.commit()
    return JSONResponse({"reserve": player_id})


# ── Long Form: the injured list (src/team/injured_list.py) ─────────────────


def _attach_il(db, league_id: str, team_id: str, players: list[dict]) -> None:
    """Each card's injured list: the stint he's on ({kind, eligible_on,
    ready}), or the lists a hurt 40-man player could go on (il_kinds)."""
    il = InjuredList(db, league_id)
    today = league_today(db, league_id)
    stints = il.for_team(team_id)
    ready = il.ready(team_id, today)
    types = InjuryRepository(db, league_id).get_team_injury_types(team_id)
    for p in players:
        st = stints.get(p["player_id"])
        if st:
            p["il"] = {
                "kind": st.kind,
                "eligible_on": st.eligible_on,
                "ready": p["player_id"] in ready,
            }
        elif p.get("injured") and p.get("roster_status") in ("26man", "40man"):
            p["il_kinds"] = kinds_for(p.get("position"), types.get(p["player_id"]))


@router.post("/leagues/{league_id}/roster/{player_id}/il")
def place_on_il(
    league_id: str,
    player_id: str,
    body: InjuredListRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    """Long Form: put a hurt player on the injured list. He comes off the
    active roster (and out of the rotation and bullpen); the 60-day list
    frees his 40-man spot too."""
    team_id = gm["team_id"]
    league = LeagueRepository(db).get_by_id(league_id)
    if not league or is_blitz_style(league.get("mode")):
        return JSONResponse(
            {"detail": "Only Long Form leagues have an injured list."}, status_code=422
        )
    il = InjuredList(db, league_id)
    today = league_today(db, league_id)
    problem = il.problem_placing(team_id, player_id, body.kind, today)
    if problem:
        return JSONResponse({"detail": problem}, status_code=422)
    stint = il.place(team_id, player_id, body.kind, today)
    _leave_staff(db, league_id, team_id, player_id)
    db.commit()
    return JSONResponse(
        {
            "kind": stint.kind,
            "placed_on": stint.placed_on,
            "eligible_on": stint.eligible_on,
        }
    )


@router.post("/leagues/{league_id}/roster/{player_id}/activate")
def activate_from_il(
    league_id: str,
    player_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    """Long Form: take a healed player off the injured list once his days
    are up. He goes back on the active roster if there's room for him,
    otherwise to the 40-man reserve."""
    team_id = gm["team_id"]
    league = LeagueRepository(db).get_by_id(league_id)
    if not league or is_blitz_style(league.get("mode")):
        return JSONResponse(
            {"detail": "Only Long Form leagues have an injured list."}, status_code=422
        )
    il = InjuredList(db, league_id)
    today = league_today(db, league_id)
    status_repo = PlayerStatusRepository(db)
    forty = set(status_repo.get_by_team_and_status(team_id, "26man")) | set(
        status_repo.get_by_team_and_status(team_id, "40man")
    )
    counted = len(forty - il.sixty_ids(team_id))
    problem = il.problem_activating(team_id, player_id, today, counted < 40)
    if problem:
        return JSONResponse({"detail": problem}, status_code=422)
    il.activate(player_id, today)
    limits = league_active_limits(db, dict(league))
    active = status_repo.get_by_team_and_status(team_id, "26man")
    rows = db.execute(
        "SELECT id, position FROM players WHERE id = ANY(%s)", (active + [player_id],)
    ).fetchall()
    pitcher = {r["id"]: is_pitcher((r["position"] or "").lower()) for r in rows}
    pitchers = sum(1 for pid in active if pitcher.get(pid))
    room = len(active) < limits.max_active and (
        not pitcher.get(player_id) or pitchers < limits.max_pitchers
    )
    to = "26man" if room else "40man"
    status_repo.set_status(player_id, to)
    db.commit()
    return JSONResponse({"to": to})


def _leave_staff(db, league_id: str, team_id: str, player_id: str) -> None:
    """A player who can't play leaves the rotation and his bullpen role, so
    the sim never hands him the ball."""
    season_id = SeasonRepository(db).get_most_recent_season_from_league(league_id)
    if not season_id:
        return
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
