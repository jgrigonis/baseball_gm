# src/api/services/free_agents.py
"""
Releasing players and signing free agents.

- Release: a GM lets one of his players go. He becomes a free agent anyone
  can sign. A guaranteed deal (he's been on the 40-man under it) stays on the
  team's payroll as dead money for the seasons it had left; a minors player
  who never made the 40-man costs nothing. Released off the 40-man, he goes
  on waivers first (src/api/services/waivers.py). When he signs elsewhere,
  his new salary comes off what his old team owes (full offset, Josh
  2026-11-05).
- Sign: a GM signs a free agent at his asking price, a standard deal priced
  from his grade and age (src/player/contracts.py). It starts this season,
  is guaranteed, and he joins the organization (minors) like a traded player.
  The minors can hold MINORS_LIMIT players, so a full team releases first.
  Going over the cap or the owner's budget is allowed (past the owner's
  hard limit it isn't: src/league/budget.py refusal); the confirm warns
  about the luxury tax and the owner.

Both wait for any sim in the league to finish (the league lock), and neither
works in a lobby or a finished league. Bidding and AI GMs signing free
agents are later phases.
"""

from __future__ import annotations

import random
from datetime import date
from src.api.services import trades, waivers
from src.db.locks import league_lock
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import FORTY_MAN_STATUSES, ContractRepository
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


# Free agency bargains (Josh, 2026-11-07: "people should be getting picked
# up off there for cheap"). A free agent still unsigned once offseason
# bidding is over asks MARKET_STEP less as the preseason starts, and another
# MARKET_STEP each MARKET_STEP_DAYS of the season, down to MARKET_FLOOR of
# his price. A fringe player (FRINGE_GRADE or worse) asks the minimum, for
# one season, any time.
MARKET_STEP = 0.10
MARKET_STEP_DAYS = 7
MARKET_FLOOR = 0.50
FRINGE_GRADE = "C-"


def is_fringe(player) -> bool:
    """C- or worse: the kind of player free agency has plenty of."""
    kind = "pitcher" if player.is_pitcher() else "hitter"
    return ct.grade_position(role_rating(player), kind) >= ct.GRADES.index(FRINGE_GRADE)


def asking_deal(
    player, year: int, scale: float = 1.0, discount: float = 1.0
) -> ct.Deal:
    """What a free agent asks for: a standard deal at his value, times how
    far his price has fallen (market_discount), or the minimum for one
    season when he's a fringe player. The same for a whole step, so the
    price doesn't change each time you look. scale is the league's
    price_scale for the season."""
    if is_fringe(player):
        return ct.Deal(ct.round_salary(ct.MIN_SALARY * scale, scale), 1, "standard")
    kind = "pitcher" if player.is_pitcher() else "hitter"
    rng = random.Random(f"ask:{player.id}:{year}")
    deal = ct.standard_deal(player.age, role_rating(player), kind, rng, scale)
    if discount >= 1.0:
        return deal
    return ct.Deal(
        ct.round_salary(deal.salary * discount, scale), deal.years, deal.kind
    )


def discount_for(state: str | None, days_played: int) -> float:
    """How far free agents' prices have fallen: full price through the
    offseason and its bidding, a step off in the preseason, then another
    step every MARKET_STEP_DAYS of the season, to the floor."""
    if state not in ("preseason", "season", "playoffs"):
        return 1.0
    steps = 1 + (max(0, days_played) // MARKET_STEP_DAYS if state != "preseason" else 0)
    return max(MARKET_FLOOR, 1.0 - MARKET_STEP * steps)


def market_discount(conn, league_id: str) -> float:
    """discount_for the league as it stands: its state, and how many days
    of the regular season have been played."""
    league = LeagueRepository(conn).get_by_id(league_id)
    state = league["state"] if league else None
    if state not in ("season", "playoffs"):
        return discount_for(state, 0)
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    row = conn.execute(
        """SELECT MIN(game_date) AS first,
                  MAX(game_date) FILTER (WHERE completed = 1) AS last
           FROM games WHERE season_id = %s AND series_id IS NULL""",
        (season_id,),
    ).fetchone()
    if not row or not row["first"] or not row["last"]:
        return discount_for(state, 0)
    days = (
        date.fromisoformat(str(row["last"])) - date.fromisoformat(str(row["first"]))
    ).days
    return discount_for(state, days)


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
    up = PlayerStatusRepository(conn).get_status(player_id) in FORTY_MAN_STATUSES
    return {
        "waivers": up,
        **_owed_view(ContractRepository(conn).release_cost(player_id, year)),
    }


def release(conn, league_id: str, team_id: str, player_id: str) -> dict:
    """Release him to free agency. Returns what the team still owes him."""
    with league_lock(conn, league_id):
        season_id, year = _context(conn, league_id)
        if not _on_team(conn, team_id, player_id):
            raise FreeAgentError("He isn't on your team.")
        player = PlayerRepository(conn).look_up(player_id)
        status_repo = PlayerStatusRepository(conn)
        was_up = status_repo.get_status(player_id) in FORTY_MAN_STATUSES
        owed = ContractRepository(conn).release(player_id, team_id, year)

        TeamRepository(conn).remove_player(team_id, player_id)
        status_repo.set_status(player_id, "free_agent")
        # Out of the rotation, bullpen and saved lineup from the next game,
        # and out of any trade offer he was in.
        effective = trades._next_game_date(conn, season_id)
        # Off the 40-man, he goes on waivers first (src/api/services/waivers.py).
        waiver = None
        if was_up:
            league = dict(LeagueRepository(conn).get_by_id(league_id))
            waiver = waivers.place(
                conn, league, season_id, player_id, team_id, effective
            )
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
    return {
        "name": player.name if player else "",
        "waivers": waiver is not None,
        "clears_on": waiver["clears_on"] if waiver else None,
        **_owed_view(owed),
    }


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
    _not_on_waivers(conn, player_id)
    deal = asking_deal(
        player,
        year,
        price_scale(conn, league_id, year),
        market_discount(conn, league_id),
    )
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
        standing["minors"],
    )


def sign(conn, league_id: str, team_id: str, player_id: str) -> dict:
    """Sign a free agent at his asking price."""
    with league_lock(conn, league_id):
        _, year = _context(conn, league_id)
        if LeagueRepository(conn).get_by_id(league_id)["state"] == "draft":
            # Offseason free agency (src/api/services/offseason_fa.py).
            raise FreeAgentError(
                "During the draft, free agents take bids. Make him an offer."
            )
        player = PlayerRepository(conn).look_up(player_id)
        status_repo = PlayerStatusRepository(conn)
        if (
            player is None
            or not _in_league(conn, league_id, player_id)
            or status_repo.get_status(player_id) != "free_agent"
        ):
            raise FreeAgentError("He isn't a free agent.")
        _not_on_waivers(conn, player_id)
        minors = len(status_repo.get_by_team_and_status(team_id, "minors"))
        if minors >= MINORS_LIMIT:
            raise FreeAgentError(
                f"Your minors are full ({MINORS_LIMIT}). Release someone first."
            )
        deal = asking_deal(
            player,
            year,
            price_scale(conn, league_id, year),
            market_discount(conn, league_id),
        )
        refusal = BudgetRepository(conn).refusal(league_id, team_id, year, deal.salary)
        if refusal:
            raise FreeAgentError(refusal)
        team_repo = TeamRepository(conn)
        team_repo.add_player(team_id, player_id)
        status_repo.set_status(player_id, "minors")
        contracts = ContractRepository(conn)
        contracts.sign_free_agent(player_id, league_id, team_id, deal, year)
        # Full offset: his new salary comes off what old teams still owe.
        contracts.apply_offset(player_id, year, deal.salary, year + deal.years - 1)
        conn.commit()
    return {
        "name": player.name,
        "salary_text": ct.format_salary(deal.salary),
        "years": deal.years,
    }


def _not_on_waivers(conn, player_id: str) -> None:
    w = waivers.on_waivers(conn, player_id)
    if w:
        when = (
            f"until after the games on {w['clears_on']}"
            if w["clears_on"]
            else "until this phase ends"
        )
        raise FreeAgentError(f"He's on waivers {when}. Claim him instead.")


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
