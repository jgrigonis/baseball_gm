# src/api/routers/trades.py
#
# The Trades tab: build an offer to another team (players, and draft picks if
# the league trades them), answer the offers made to you, vote on other GMs'
# trades, and the league's trade history. Rules, the
# AI's answer and the league vote live in src/api/services/trades.py.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.dependencies import DB, GM, ActiveLeague, IsHTMX, Unpaused, User
from src.api.schemas import (
    TradeOfferRequest,
    TradeShopTakeRequest,
    TradeVoteRequest,
)
from src.api.services.ready_check import is_multiplayer
from src.api.services import icons, trade_shop, trades
from src.api.services import owners as owner_service
from src.api.view_models.player_cards import (
    attach_injuries,
    attach_roster_stats,
    roster_card,
)
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.happiness_repo import HappinessRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.persona_repo import PersonaRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.trade_repo import TradeRepository
from src.league import budget as bg
from src.league import owners, trade_deadline
from src.league.trades import draft_picks
from src.team.roster_limits import (
    MAX_PLAYING_ROSTER,
    MIN_PLAYING_ROSTER,
    playing_count,
)
from src.player.contracts import format_salary
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


def team_cards(db, league_id: str, season_id: str | None, team_id: str) -> list[dict]:
    """Every player a team owns, as roster cards with injuries and this
    season's stat line."""
    cards = [
        roster_card(row)
        for row in PlayerRepository(db).get_team_roster_with_skills(team_id)
    ]
    if season_id:
        attach_roster_stats(
            cards,
            PlayerSeasonStatsRepository(db).get_team_stats_map(season_id, team_id),
        )
    inj = InjuryRepository(db, league_id)
    attach_injuries(
        cards, inj.get_team_injuries(team_id), inj.get_team_injury_types(team_id)
    )
    cards = [c for c in cards if c["roster_status"] in trades.TRADEABLE]
    attach_pay(db, league_id, cards)
    return cards


def attach_pay(db, league_id: str, cards: list[dict]) -> None:
    """Each player's salary this season, and `pay`: what he adds to a
    payroll (only a deal on the payroll counts), for the budget warnings."""
    contracts = ContractRepository(db)
    year = contracts.current_year(league_id)
    deals = (
        contracts.active_for([c["player_id"] for c in cards], year)
        if year is not None
        else {}
    )
    for c in cards:
        deal = deals.get(c["player_id"])
        c["salary_text"] = format_salary(deal["salary"]) if deal else None
        c["pay"] = deal["salary"] if deal and deal["on_payroll"] else 0


def offer_pay_change(db, league_id: str, offer: dict) -> int:
    """How much the offer adds to the receiving team's payroll: the
    payroll salaries it gets, less the ones it gives up."""
    ids = [
        i["player_id"] for i in offer["sent"] + offer["received"] if i.get("player_id")
    ]
    contracts = ContractRepository(db)
    year = contracts.current_year(league_id)
    if year is None:
        return 0
    deals = contracts.active_for(ids, year)

    def pay(items):
        return sum(
            deals[i["player_id"]]["salary"]
            for i in items
            if i.get("player_id") in deals and deals[i["player_id"]]["on_payroll"]
        )

    return pay(offer["sent"]) - pay(offer["received"])


def cap_rooms(db, league_id: str) -> dict[str, int]:
    """Each team's room under the league's cap this season (negative: over
    it), by team id. Payrolls and the cap are public (the Budget tab's
    League payrolls). Empty without budgets."""
    contracts = ContractRepository(db)
    year = contracts.current_year(league_id)
    if year is None:
        return {}
    repo = BudgetRepository(db)
    teams = repo.for_league(league_id, year)
    if not teams:
        return {}
    cap = repo.cap(league_id, year)
    return {t: cap - contracts.payroll(t, year) for t in teams}


def room_text(room: int | None) -> str | None:
    """ "$12M under the cap", "$4.5M over the cap", or None without budgets."""
    if room is None:
        return None
    if room >= 0:
        return f"{format_salary(room)} under the cap"
    return f"{format_salary(-room)} over the cap"


@router.get("/leagues/{league_id}/trades", response_class=HTMLResponse)
def trades_tab(
    request: Request,
    htmx: IsHTMX,
    db: DB,
    user: User,
    gm: GM,
    league_id: str,
):
    ctx = _shell_ctx(request, db, gm, league_id, "trades", user)
    league = LeagueRepository(db).get_by_id(league_id)
    season_id = SeasonRepository(db).get_current_id_for_league(league_id)
    team_id = gm["team_id"]

    human_teams = GMRepository(db).get_human_team_ids(league_id)
    rooms = cap_rooms(db, league_id)
    teams = (
        [
            {
                "id": t["id"],
                "name": f"{t['city']} {t['mascot']}",
                "human": t["id"] in human_teams,
                "room_text": room_text(rooms.get(t["id"])),
            }
            for t in TeamRepository(db).get_teams_in_league_season(league_id, season_id)
            if t["id"] != team_id
        ]
        if season_id
        else []
    )

    trade_repo = TradeRepository(db)
    # Payroll against budget, for the warnings (src/league/budget.py).
    year = ContractRepository(db).current_year(league_id)
    standing = (
        BudgetRepository(db).standing(league_id, team_id, year)
        if team_id and year is not None
        else None
    )
    offers_to_me = trade_repo.offers_to_team(league_id, team_id) if team_id else []
    if standing:
        for o in offers_to_me:
            o["budget_warning"] = bg.warning(
                standing["payroll"],
                standing["cap"],
                standing["budget"],
                offer_pay_change(db, league_id, o),
                standing["front_office"],
                standing["minors"],
            )
    my_players = (
        team_cards(db, league_id, season_id, team_id)
        + trades.pick_cards(db, dict(league), season_id, team_id)
        if team_id
        else []
    )
    # Franchise icons, so the builder can warn before one goes.
    icons.attach(db, team_id, my_players)
    owner = owner_service.ensure(db, league_id).get(team_id) if team_id else None
    owner_icons = bool(
        owner and owners.clean_weights(owner["weights"])["icons"] >= owners.STRONG
    )
    # Who's asked out: first in the Shop a player list, and flagged.
    asks = HappinessRepository(db, league_id).trade_requests(
        p["player_id"] for p in my_players if p.get("roster_status") != "pick"
    )
    for p in my_players:
        p["wants_trade"] = p["player_id"] in asks
    shop_players = sorted(
        (
            {
                "player_id": p["player_id"],
                "name": f"{p['first_name']} {p['last_name']}".strip(),
                "position": p.get("position") or "",
                "overall": p.get("overall") or "",
                "wants_trade": p["player_id"] in asks,
                "forty": p.get("roster_status") in ("26man", "40man"),
            }
            for p in my_players
            if p.get("roster_status") != "pick"
        ),
        key=lambda p: (not p["wants_trade"], not p["forty"], p["name"]),
    )
    ctx.update(
        {
            "shop_players": shop_players,
            # AI teams' GMs, for their names and persona cards.
            "ai_gms": PersonaRepository(db).by_team(league_id),
            "trade_window": trade_deadline.window(db, dict(league), season_id),
            "trade_teams": teams,
            "my_players": my_players,
            "pick_trades": draft_picks.enabled(dict(league)),
            "my_playing_count": playing_count(db, team_id) if team_id else 0,
            "min_roster": MIN_PLAYING_ROSTER,
            "max_roster": MAX_PLAYING_ROSTER,
            "max_per_side": trades.MAX_PER_SIDE,
            "my_offers": trade_repo.offers_for_team(league_id, team_id)
            if team_id
            else [],
            "offers_to_me": offers_to_me,
            "budget": standing,
            "owner_icons": owner_icons,
            "my_votes": trade_repo.votes_for_gm(league_id, gm["id"])
            if gm.get("id")
            else [],
            "league_trades": trade_repo.history(league_id),
            # Single player: AI offers stand for a few days.
            "solo": not is_multiplayer(db, league_id),
        }
    )
    return tab_response(request, htmx, "dashboard/partials/trades.html", ctx)


@router.get("/leagues/{league_id}/trades/inbox")
def trade_inbox(league_id: str, db: DB, gm: GM):
    """How many offers and votes are waiting on the GM: the Trades tab's
    badge."""
    return JSONResponse({"count": trades.inbox_count(db, league_id, gm)})


@router.get("/leagues/{league_id}/trades/team/{team_id}")
def trade_team_roster(league_id: str, team_id: str, db: DB, gm: GM):
    """Another team's players, for the offer builder."""
    season_id = SeasonRepository(db).get_current_id_for_league(league_id)
    if not season_id or not TeamRepository(db).is_in_league(
        team_id, league_id, season_id
    ):
        return JSONResponse(
            {"detail": "That team isn't in this league."}, status_code=404
        )
    league = dict(LeagueRepository(db).get_by_id(league_id))
    return JSONResponse(
        {
            "players": team_cards(db, league_id, season_id, team_id)
            + trades.pick_cards(db, league, season_id, team_id)
        }
    )


@router.post("/leagues/{league_id}/trades")
def propose_trade(
    league_id: str,
    body: TradeOfferRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _unpaused: Unpaused,
):
    """Offer players to another team, or counter an offer made to you. An AI
    team's answer comes straight back; another GM's comes later."""
    try:
        result = trades.propose(
            db,
            league_id,
            gm,
            body.to_team_id,
            body.give,
            body.get,
            counter_of=body.counter_of,
        )
    except trades.TradeError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    return JSONResponse(result)


@router.post("/leagues/{league_id}/trades/shop/{player_id}")
def shop_player(
    league_id: str,
    player_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _unpaused: Unpaused,
):
    """Every AI team's best offer for one of your players, each with the
    players it would send as roster cards. (Before the routes below, which
    would take "shop" for an offer.)"""
    try:
        result = trade_shop.shop(db, league_id, gm, player_id)
    except trades.TradeError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    season_id = SeasonRepository(db).get_current_id_for_league(league_id)
    ai_gms = PersonaRepository(db).by_team(league_id)
    rooms = cap_rooms(db, league_id)
    for o in result["offers"] + result["close"]:
        cards = {
            c["player_id"]: c
            for c in team_cards(db, league_id, season_id, o["team_id"])
        }
        o["players"] = [cards[pid] for pid in o["give"] if pid in cards]
        o["room_text"] = room_text(rooms.get(o["team_id"]))
        g = ai_gms.get(o["team_id"])
        o["gm_name"] = g["name"] if g else None
    return JSONResponse(result)


@router.post("/leagues/{league_id}/trades/shop/{player_id}/take")
def take_shop_offer(
    league_id: str,
    player_id: str,
    body: TradeShopTakeRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _unpaused: Unpaused,
):
    """Trade your player for an AI team's shop offer, worked out again now.
    Answers like an offer to an AI team."""
    try:
        result = trade_shop.take(db, league_id, gm, player_id, body.team_id)
    except trades.TradeError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    return JSONResponse(result)


@router.post("/leagues/{league_id}/trades/shop/{player_id}/dump")
def dump_player(
    league_id: str,
    player_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _unpaused: Unpaused,
):
    """What every AI team would take one of your players' salary for: the
    throw-in it sends back and any sweetener you'd add, as roster cards."""
    try:
        result = trade_shop.dump(db, league_id, gm, player_id)
    except trades.TradeError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    season_id = SeasonRepository(db).get_current_id_for_league(league_id)
    ai_gms = PersonaRepository(db).by_team(league_id)
    mine = {
        c["player_id"]: c for c in team_cards(db, league_id, season_id, gm["team_id"])
    }
    rooms = cap_rooms(db, league_id)
    for o in result["offers"]:
        cards = {
            c["player_id"]: c
            for c in team_cards(db, league_id, season_id, o["team_id"])
        }
        o["players"] = [cards[pid] for pid in o["give"] if pid in cards]
        o["adds"] = [mine[pid] for pid in o["add"] if pid in mine]
        o["saved_text"] = format_salary(o["saved"])
        o["room_text"] = room_text(rooms.get(o["team_id"]))
        g = ai_gms.get(o["team_id"])
        o["gm_name"] = g["name"] if g else None
    result["salary_text"] = format_salary(result["salary"])
    return JSONResponse(result)


@router.post("/leagues/{league_id}/trades/shop/{player_id}/dump/take")
def take_dump_offer(
    league_id: str,
    player_id: str,
    body: TradeShopTakeRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _unpaused: Unpaused,
):
    """Trade your player (and any sweetener) for an AI team's dump offer,
    worked out again now. Answers like an offer to an AI team."""
    try:
        result = trade_shop.dump_take(db, league_id, gm, player_id, body.team_id)
    except trades.TradeError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    return JSONResponse(result)


@router.post("/leagues/{league_id}/trades/{offer_id}/vote")
def vote_on_trade(
    league_id: str,
    offer_id: str,
    body: TradeVoteRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _unpaused: Unpaused,
):
    """Your vote on a trade between two other GMs. (Before the route
    below, which would take "vote" for an action.)"""
    try:
        return JSONResponse(trades.vote(db, league_id, gm, offer_id, body.yes))
    except trades.TradeError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)


@router.post("/leagues/{league_id}/trades/{offer_id}/{action}")
def answer_trade(
    league_id: str,
    offer_id: str,
    action: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _unpaused: Unpaused,
):
    """Accept or reject an offer made to you, or withdraw one you made."""
    if action not in ("accept", "reject", "withdraw"):
        return JSONResponse({"detail": "Unknown action."}, status_code=404)
    try:
        return JSONResponse(trades.respond(db, league_id, gm, offer_id, action))
    except trades.TradeError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
