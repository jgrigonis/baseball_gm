# src/api/services/free_agents.py
"""
Releasing players and signing free agents.

- Release: a GM lets one of his players go. He becomes a free agent anyone
  can sign. A guaranteed deal (he's been on the 40-man under it) stays on the
  team's payroll as dead money for the seasons it had left; a minors player
  who never made the 40-man costs nothing. (Josh's decisions, 2026-11-04:
  the old team owes all of it for now, with an offset for what his new team
  pays coming later.)
- Sign: a GM signs a free agent at his asking price, a standard deal priced
  from his grade and age (src/player/contracts.py). It starts this season,
  is guaranteed, and he joins the organization (minors) like a traded player.
  The minors can hold MINORS_LIMIT players, so a full team releases first.
  Going over the cap or the owner's budget is allowed (past the owner's
  hard limit it isn't: src/league/budget.py refusal); the confirm warns
  about the luxury tax and the owner.

Both wait for any sim in the league to finish (the league lock), and neither
works in a lobby or a finished league. Waivers, bidding and AI GMs signing
free agents are later phases.
"""

from __future__ import annotations

import random
from src.api.services import trades
from src.db.locks import league_lock
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.league import budget as bg
from src.league.offseason.roster_trimmer import MINORS_LIMIT
from src.player import contracts as ct
from src.player.player_value import role_rating

# League states a GM can release or sign in.
OPEN_STATES = ("preseason", "season", "playoffs", "offseason", "draft")


class FreeAgentError(Exception):
    """A release or signing that can't happen, with the reason to show."""


def asking_deal(player, year: int, scale: float = 1.0) -> ct.Deal:
    """What a free agent asks for: a standard deal at his value. The same
    all season, so the price doesn't change each time you look. scale is
    the league's price_scale for the season."""
    kind = "pitcher" if player.is_pitcher() else "hitter"
    rng = random.Random(f"ask:{player.id}:{year}")
    return ct.standard_deal(player.age, role_rating(player), kind, rng, scale)


def price_scale(conn, league_id: str, year: int) -> float:
    """How far contract prices have grown with the league's cap."""
    return BudgetRepository(conn).salary_scale(league_id, year)


def _context(conn, league_id: str) -> tuple[str, int]:
    """The league's current season and its year, or FreeAgentError when
    the league isn't somewhere players can move."""
    league = LeagueRepository(conn).get_by_id(league_id)
    if not league or league["state"] not in OPEN_STATES:
        raise FreeAgentError("Players can't be released or signed right now.")
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    year = ContractRepository(conn).current_year(league_id)
    if not season_id or year is None:
        raise FreeAgentError("Players can't be released or signed right now.")
    return season_id, year


def release_preview(conn, league_id: str, team_id: str, player_id: str) -> dict:
    """What releasing him would cost, for the confirm dialog."""
    _, year = _context(conn, league_id)
    if not _on_team(conn, team_id, player_id):
        raise FreeAgentError("He isn't on your team.")
    return _owed_view(ContractRepository(conn).release_cost(player_id, year))


def release(conn, league_id: str, team_id: str, player_id: str) -> dict:
    """Release him to free agency. Returns what the team still owes him."""
    with league_lock(conn, league_id):
        season_id, year = _context(conn, league_id)
        if not _on_team(conn, team_id, player_id):
            raise FreeAgentError("He isn't on your team.")
        player = PlayerRepository(conn).look_up(player_id)
        owed = ContractRepository(conn).release(player_id, team_id, year)

        TeamRepository(conn).remove_player(team_id, player_id)
        PlayerStatusRepository(conn).set_status(player_id, "free_agent")
        # Out of the rotation, bullpen and saved lineup from the next game,
        # and out of any trade offer he was in.
        effective = trades._next_game_date(conn, season_id)
        trades._clear_roles(conn, team_id, season_id, [player_id], effective)
        trade_repo = trades.TradeRepository(conn)
        for offer_id in trade_repo.open_offers_with_players(league_id, [player_id]):
            trades._void(
                conn,
                league_id,
                trade_repo.get(offer_id),
                "a player in it was released.",
            )
        conn.commit()
    return {"name": player.name if player else "", **_owed_view(owed)}


def sign_preview(conn, league_id: str, team_id: str, player_id: str) -> dict:
    """What signing him would cost, for the confirm: his asking deal, and a
    warning when it takes the team over budget (src/league/budget.py)."""
    _, year = _context(conn, league_id)
    player = PlayerRepository(conn).look_up(player_id)
    if (
        player is None
        or not _in_league(conn, league_id, player_id)
        or PlayerStatusRepository(conn).get_status(player_id) != "free_agent"
    ):
        raise FreeAgentError("He isn't a free agent.")
    deal = asking_deal(player, year, price_scale(conn, league_id, year))
    return {
        "salary_text": ct.format_salary(deal.salary),
        "years": deal.years,
        "warning": budget_warning(conn, league_id, team_id, year, deal.salary),
        "blocked": BudgetRepository(conn).refusal(
            league_id, team_id, year, deal.salary
        ),
    }


def budget_warning(
    conn, league_id: str, team_id: str, year: int, added: int
) -> str | None:
    """The over-budget warning for adding this much payroll, if any."""
    standing = BudgetRepository(conn).standing(league_id, team_id, year)
    if standing is None:
        return None
    return bg.warning(
        standing["payroll"],
        standing["cap"],
        standing["budget"],
        added,
        standing["front_office"],
    )


def sign(conn, league_id: str, team_id: str, player_id: str) -> dict:
    """Sign a free agent at his asking price."""
    with league_lock(conn, league_id):
        _, year = _context(conn, league_id)
        player = PlayerRepository(conn).look_up(player_id)
        status_repo = PlayerStatusRepository(conn)
        if (
            player is None
            or not _in_league(conn, league_id, player_id)
            or status_repo.get_status(player_id) != "free_agent"
        ):
            raise FreeAgentError("He isn't a free agent.")
        minors = len(status_repo.get_by_team_and_status(team_id, "minors"))
        if minors >= MINORS_LIMIT:
            raise FreeAgentError(
                f"Your minors are full ({MINORS_LIMIT}). Release someone first."
            )
        deal = asking_deal(player, year, price_scale(conn, league_id, year))
        refusal = BudgetRepository(conn).refusal(league_id, team_id, year, deal.salary)
        if refusal:
            raise FreeAgentError(refusal)
        team_repo = TeamRepository(conn)
        team_repo.add_player(team_id, player_id)
        status_repo.set_status(player_id, "minors")
        ContractRepository(conn).sign_free_agent(
            player_id, league_id, team_id, deal, year
        )
        conn.commit()
    return {
        "name": player.name,
        "salary_text": ct.format_salary(deal.salary),
        "years": deal.years,
    }


def _on_team(conn, team_id: str, player_id: str) -> bool:
    return player_id in PlayerRepository(conn).get_player_ids_from_team_players(team_id)


def _in_league(conn, league_id: str, player_id: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM players WHERE id = %s AND league_id = %s",
            (player_id, league_id),
        ).fetchone()
    )


def _owed_view(owed: dict) -> dict:
    return {
        **owed,
        "salary_text": ct.format_salary(owed["salary"]) if owed["salary"] else None,
        "total_text": ct.format_salary(owed["total"]) if owed["total"] else None,
    }
