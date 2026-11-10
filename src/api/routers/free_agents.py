# src/api/routers/free_agents.py
#
# The Free Agents tab, and releasing and signing players
# (src/api/services/free_agents.py).

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from src.api.dependencies import DB, GM, ActiveLeague, GMOrViewer, IsHTMX, User
from src.api.services import free_agents, icons, offseason_fa, waivers
from src.api.view_models.player_cards import (
    attach_injuries,
    attach_roster_stats,
    roster_card,
)
from src.db.locks import league_lock
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.waiver_repo import WaiverRepository
from src.league.offseason.roster_trimmer import MINORS_LIMIT
from src.player.contracts import format_salary
from src.player.face import face_url
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])

# The tab lists this many free agents, the best (by grade) first. The rest of the pool
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
    # Best first is by the grade shown on each row (Josh, 2026-11-05), then
    # how far into that grade he is (grade_curves.overall_score).
    # Players on waivers come first: they're only there for a few days.
    on_waivers = {w["player_id"]: w for w in WaiverRepository(db).open_for(league_id)}
    cards = sorted(
        ((roster_card(row), row) for row in rows),
        key=lambda c: (
            c[1]["id"] not in on_waivers,
            -c[0].get("overall_score", -1.0),
        ),
    )
    shown = cards[: max(MAX_SHOWN, len(on_waivers))]
    team_id = gm.get("team_id") if gm else None
    my_claims = WaiverRepository(db).claims_by(league_id, team_id) if team_id else set()

    last_team = contracts.last_team([r["id"] for _, r in shown])
    names = TeamRepository(db).get_names(list(set(last_team.values())))
    players = []
    scale = free_agents.price_scale(db, league_id, year) if year is not None else 1.0
    shifts = free_agents.price_shifts(db, league_id, year) if year is not None else {}
    discount = free_agents.market_discount(db, league_id)
    for card, row in shown:
        record = player_repo.record_from_row(row)
        card["face_url"] = face_url(row["id"], card.get("age"), None, None)
        w = on_waivers.get(row["id"])
        if w and year is not None:
            # On waivers: a claim takes over the deal he has.
            view = waivers.deal_view(
                contracts.released_deal(row["id"], w["from_team_id"]), year
            )
            card["salary"] = view.get("salary")
            card["salary_text"] = view["salary_text"]
            card["ask_years"] = view["years_left"]
            card["waiver"] = {
                "clears_text": waivers.clears_text(w),
                "claimed": row["id"] in my_claims,
                "mine": w["from_team_id"] == team_id,
            }
        elif year is not None:
            deal = free_agents.asking_deal(record, year, scale, discount, shifts)
            card["salary"] = deal.salary
            card["salary_text"] = format_salary(deal.salary)
            card["ask_years"] = deal.years
        last = last_team.get(row["id"])
        card["last_team"] = names.get(last) if last else None
        players.append(card)
    # Our own franchise icons in the pool (let go or released), tagged like
    # Roster and Lineup (Josh, 2026-11-10).
    icons.attach(db, team_id, players)

    # Offseason free agency (src/api/services/offseason_fa.py): bids during
    # the draft, and the GM's expiring deals in the offseason.
    state = ctx.get("league_state")
    ctx["bidding"] = state == "draft"
    if ctx["bidding"] and year is not None:
        counts = offseason_fa.bid_counts(db, league_id, year)
        mine = offseason_fa.bids_by(db, league_id, team_id, year) if team_id else {}
        for card in players:
            pid = card["player_id"]
            card["bids"] = counts.get(pid, 0)
            b = mine.get(pid)
            if b:
                card["my_bid"] = {
                    "salary_text": format_salary(b["salary"]),
                    "years": b["years"],
                }
    ctx["expiring"] = []
    if state == "offseason" and team_id and not ctx.get("is_viewer"):
        for e in offseason_fa.expiring_view(db, league_id, team_id):
            row = player_repo.get_with_skills(e["player_id"])
            if not row:
                continue
            row["status"] = e["status"]
            card = roster_card(row)
            card["face_url"] = face_url(row["id"], card.get("age"), None, None)
            card.update(e)
            ctx["expiring"].append(card)
        ctx["expiring"].sort(key=lambda c: -c.get("overall_score", -1.0))
        # The season just played, and who's hurt (Josh, 2026-11-09).
        exp = ctx["expiring"]
        if exp and ctx.get("season_id"):
            attach_roster_stats(
                exp,
                PlayerSeasonStatsRepository(db).get_team_stats_map(
                    ctx["season_id"], team_id
                ),
            )
        if exp:
            inj = InjuryRepository(db, league_id)
            attach_injuries(
                exp,
                inj.get_team_injuries(team_id),
                inj.get_team_injury_types(team_id),
            )
        # Franchise icons whose deals are up (Josh, 2026-11-10).
        icons.attach(db, team_id, exp)
        if ctx["expiring"]:
            ctx["next_money"] = offseason_fa.next_season_money(db, league_id, team_id)
            ctx["resign_all"] = offseason_fa.resign_all_plan(db, league_id, team_id)

    ctx["players"] = players
    ctx["market_step_pct"] = round(free_agents.MARKET_STEP * 100)
    ctx["market_floor_pct"] = round(free_agents.MARKET_FLOOR * 100)
    ctx["pool_size"] = len(rows)
    ctx["max_shown"] = MAX_SHOWN
    ctx["market_seasons"] = offseason_fa.MARKET_SEASONS
    ctx["minors_limit"] = MINORS_LIMIT
    ctx["waiver_count"] = len(on_waivers)
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
    """His asking deal and any over-budget warning, for the confirm. During
    the draft, what a bid needs instead (offseason_fa.py)."""
    if (LeagueRepository(db).get_by_id(league_id) or {}).get("state") == "draft":
        try:
            result = offseason_fa.bid_preview(db, league_id, gm["team_id"], player_id)
        except offseason_fa.OffseasonFAError as e:
            return JSONResponse({"detail": str(e)}, status_code=422)
        return JSONResponse({"bidding": True, **result})
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


@router.get("/leagues/{league_id}/waivers/{player_id}/claim")
def claim_preview(league_id: str, player_id: str, db: DB, gm: GM):
    """His deal and when he clears, for the claim confirm."""
    year = ContractRepository(db).current_year(league_id)
    try:
        result = waivers.claim_preview(db, league_id, gm["team_id"], player_id, year)
    except waivers.WaiverError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    result["warning"] = (
        free_agents.budget_warning(
            db, league_id, gm["team_id"], year, result.get("salary") or 0
        )
        if result.get("years_left")
        else None
    )
    return JSONResponse(result)


@router.post("/leagues/{league_id}/waivers/{player_id}/claim")
def claim_off_waivers(
    league_id: str, player_id: str, db: DB, gm: GM, _active: ActiveLeague
):
    year = ContractRepository(db).current_year(league_id)
    try:
        with league_lock(db, league_id):
            result = waivers.claim(db, league_id, gm["team_id"], player_id, year)
            db.commit()
    except waivers.WaiverError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    return JSONResponse(result)


@router.post("/leagues/{league_id}/waivers/{player_id}/withdraw")
def withdraw_claim(
    league_id: str, player_id: str, db: DB, gm: GM, _active: ActiveLeague
):
    with league_lock(db, league_id):
        waivers.withdraw(db, league_id, gm["team_id"], player_id)
        db.commit()
    return JSONResponse({"ok": True})


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


# ── Offseason free agency (src/api/services/offseason_fa.py) ─────────────────


def _expiring_result(db, league_id: str, team_id: str, result: dict) -> dict:
    """Every expiring row's call and fate, since one call moves the room for
    the rest, the room line, and the Re-sign All plan, for the Free Agents
    tab to update in place."""
    result["rows"] = {
        e["player_id"]: {"choice": e["choice"], "fate": e["fate"]}
        for e in offseason_fa.expiring_view(db, league_id, team_id)
    }
    result["money"] = offseason_fa.next_season_money(db, league_id, team_id)
    result["all"] = offseason_fa.resign_all_plan(db, league_id, team_id)
    return result


class BidBody(BaseModel):
    salary: int
    years: int


@router.post("/leagues/{league_id}/free-agents/{player_id}/bid")
def place_bid(
    league_id: str, player_id: str, body: BidBody, db: DB, gm: GM, _active: ActiveLeague
):
    try:
        result = offseason_fa.place_bid(
            db, league_id, gm["team_id"], player_id, body.salary, body.years
        )
    except offseason_fa.OffseasonFAError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    return JSONResponse(_expiring_result(db, league_id, gm["team_id"], result))


@router.post("/leagues/{league_id}/free-agents/{player_id}/bid/withdraw")
def withdraw_bid(league_id: str, player_id: str, db: DB, gm: GM, _active: ActiveLeague):
    offseason_fa.withdraw_bid(db, league_id, gm["team_id"], player_id)
    return JSONResponse({"ok": True})


class ChoiceBody(BaseModel):
    choice: str | None = None


@router.post("/leagues/{league_id}/expiring/resign-all")
def resign_all_expiring(league_id: str, db: DB, gm: GM, _active: ActiveLeague):
    """Re-sign every expiring deal at once."""
    try:
        result = offseason_fa.resign_all(db, league_id, gm["team_id"])
    except offseason_fa.OffseasonFAError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    return JSONResponse(_expiring_result(db, league_id, gm["team_id"], result))


@router.post("/leagues/{league_id}/players/{player_id}/expiring")
def expiring_choice(
    league_id: str,
    player_id: str,
    body: ChoiceBody,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    """Re-sign an expiring player now, let him go, or undo the call."""
    try:
        result = offseason_fa.choose(
            db, league_id, gm["team_id"], player_id, body.choice
        )
    except offseason_fa.OffseasonFAError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    return JSONResponse(_expiring_result(db, league_id, gm["team_id"], result))
