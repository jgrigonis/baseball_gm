# src/api/routers/free_agents.py
#
# The Free Agents tab, and releasing and signing players
# (src/api/services/free_agents.py).

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.dependencies import DB, GM, ActiveLeague, GMOrViewer, IsHTMX, User
from src.api.services import free_agents
from src.api.view_models.player_cards import roster_card
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.team_repo import TeamRepository
from src.league.offseason.roster_trimmer import MINORS_LIMIT
from src.player.contracts import format_salary
from src.player.face import face_url
from src.player.player_value import role_rating
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])

# The tab lists this many free agents, the best first. The rest of the pool
# is mostly prospects nobody kept.
MAX_SHOWN = 300


@router.get("/leagues/{league_id}/free-agents", response_class=HTMLResponse)
def free_agents_tab(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
):
    ctx = _shell_ctx(request, db, gm, league_id, "free-agents", user)
    contracts = ContractRepository(db)
    year = contracts.current_year(league_id)
    player_repo = PlayerRepository(db)

    rows = player_repo.get_free_agents_with_skills(league_id)
    rated = []
    for row in rows:
        record = player_repo.record_from_row(row)
        rated.append((role_rating(record), row, record))
    rated.sort(key=lambda r: -r[0])
    shown = rated[:MAX_SHOWN]

    last_team = contracts.last_team([r[1]["id"] for r in shown])
    names = TeamRepository(db).get_names(list(set(last_team.values())))
    players = []
    for _, row, record in shown:
        card = roster_card(row)
        card["face_url"] = face_url(row["id"], card.get("age"), None, None)
        if year is not None:
            deal = free_agents.asking_deal(record, year)
            card["salary"] = deal.salary
            card["salary_text"] = format_salary(deal.salary)
            card["ask_years"] = deal.years
        team_id = last_team.get(row["id"])
        card["last_team"] = names.get(team_id) if team_id else None
        players.append(card)

    ctx["players"] = players
    ctx["pool_size"] = len(rows)
    ctx["max_shown"] = MAX_SHOWN
    ctx["minors_limit"] = MINORS_LIMIT
    team_id = gm.get("team_id") if gm else None
    ctx["can_sign"] = bool(team_id) and not ctx.get("is_viewer")
    if ctx["can_sign"] and year is not None:
        ctx["minors_count"] = len(
            PlayerStatusRepository(db).get_by_team_and_status(team_id, "minors")
        )
        ctx["payroll_text"] = format_salary(contracts.payroll(team_id, year))
        ctx["budget"] = BudgetRepository(db).standing(league_id, team_id, year)
    return tab_response(request, htmx, "dashboard/partials/free_agents.html", ctx)


@router.get("/leagues/{league_id}/free-agents/{player_id}/sign")
def sign_preview(league_id: str, player_id: str, db: DB, gm: GM):
    """His asking deal and any over-budget warning, for the confirm."""
    try:
        result = free_agents.sign_preview(db, league_id, gm["team_id"], player_id)
    except free_agents.FreeAgentError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    return JSONResponse(result)


@router.post("/leagues/{league_id}/free-agents/{player_id}/sign")
def sign_free_agent(
    league_id: str, player_id: str, db: DB, gm: GM, _active: ActiveLeague
):
    try:
        result = free_agents.sign(db, league_id, gm["team_id"], player_id)
    except free_agents.FreeAgentError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    return JSONResponse(result)


@router.get("/leagues/{league_id}/players/{player_id}/release")
def release_preview(league_id: str, player_id: str, db: DB, gm: GM):
    """What releasing him would leave on the books, for the confirm."""
    try:
        cost = free_agents.release_preview(db, league_id, gm["team_id"], player_id)
    except free_agents.FreeAgentError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    return JSONResponse(cost)


@router.post("/leagues/{league_id}/players/{player_id}/release")
def release_player(
    league_id: str, player_id: str, db: DB, gm: GM, _active: ActiveLeague
):
    try:
        result = free_agents.release(db, league_id, gm["team_id"], player_id)
    except free_agents.FreeAgentError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    return JSONResponse(result)
