# src/api/routers/trades.py
#
# The Trades tab: build an offer to an AI team, see its answer, and the
# league's trade history. Rules and the AI's answer live in
# src/api/services/trades.py.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.dependencies import DB, GM, ActiveLeague, IsHTMX, Unpaused, User
from src.api.schemas import TradeOfferRequest
from src.api.services import trades
from src.api.view_models.player_cards import (
    attach_injuries,
    attach_roster_stats,
    roster_card,
)
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.trade_repo import TradeRepository
from src.league import trade_deadline
from src.team.roster_limits import (
    MAX_PLAYING_ROSTER,
    MIN_PLAYING_ROSTER,
    playing_count,
)
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
    attach_injuries(cards, InjuryRepository(db, league_id).get_team_injuries(team_id))
    return [c for c in cards if c["roster_status"] in trades.TRADEABLE]


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
    teams = (
        [
            {
                "id": t["id"],
                "name": f"{t['city']} {t['mascot']}",
                "human": t["id"] in human_teams,
            }
            for t in TeamRepository(db).get_teams_in_league_season(league_id, season_id)
            if t["id"] != team_id
        ]
        if season_id
        else []
    )

    trade_repo = TradeRepository(db)
    ctx.update(
        {
            "trade_window": trade_deadline.window(db, dict(league), season_id),
            "trade_teams": teams,
            "my_players": team_cards(db, league_id, season_id, team_id)
            if team_id
            else [],
            "my_playing_count": playing_count(db, team_id) if team_id else 0,
            "min_roster": MIN_PLAYING_ROSTER,
            "max_roster": MAX_PLAYING_ROSTER,
            "max_per_side": trades.MAX_PER_SIDE,
            "my_offers": trade_repo.offers_from_team(league_id, team_id)
            if team_id
            else [],
            "league_trades": trade_repo.history(league_id),
        }
    )
    return tab_response(request, htmx, "dashboard/partials/trades.html", ctx)


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
    return JSONResponse({"players": team_cards(db, league_id, season_id, team_id)})


@router.post("/leagues/{league_id}/trades")
def propose_trade(
    league_id: str,
    body: TradeOfferRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _unpaused: Unpaused,
):
    """Offer players to an AI team. Its answer comes straight back."""
    try:
        result = trades.propose(db, league_id, gm, body.to_team_id, body.give, body.get)
    except trades.TradeError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)
    return JSONResponse(result)
