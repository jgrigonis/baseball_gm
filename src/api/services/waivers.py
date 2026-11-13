# src/api/services/waivers.py
"""
Waivers (free agency phase 2; Josh's decisions, 2026-11-05).

- A player released off the 40-man, or with a guaranteed deal, goes on
  waivers for WAIVER_PERIODS sim periods of game days
  (free_agents.goes_on_waivers). Minors players on deals that were never
  guaranteed skip waivers: releasing them is free, and they're free agents
  at once.
- Any other team can claim him while he's on waivers. When he clears, the
  claiming team with the worst record gets him (last season's record before
  any games this season), and takes over his whole deal, so his old team
  owes nothing. He joins the organization (minors) like a signing.
- Nobody claimed him: he's a free agent, and his old team keeps paying until
  he signs elsewhere (the offset, ContractRepository.apply_offset).
- Outside game days (offseason, draft, or with too few game days left),
  waivers clear when the phase ends: end of the playoffs, start of the
  draft, end of the draft.

A claim must fit the team: room in the minors and inside the owner's hard
limit (src/league/budget.py refusal), checked again when he clears.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

from src.api.services import front_office
from src.api.services.news import moves as move_news
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.waiver_repo import WaiverRepository
from src.league import prorate
from src.league.offseason.roster_trimmer import MINORS_LIMIT
from src.player import contracts as ct

# How long a player sits on waivers, in sim periods of game days.
WAIVER_PERIODS = 2


class WaiverError(Exception):
    """A claim that can't happen, with the reason to show."""


def _game_days_ahead(conn, season_id: str) -> list[str]:
    rows = conn.execute(
        """SELECT DISTINCT game_date FROM games
           WHERE season_id = %s AND completed = 0
           ORDER BY game_date""",
        (season_id,),
    ).fetchall()
    return [r["game_date"] for r in rows]


def clears_on(conn, league: dict, season_id: str) -> str | None:
    """The day he clears, after its games: WAIVER_PERIODS sim periods of game
    days from now. None when there aren't that many game days ahead (he
    clears when the phase ends)."""
    days = int(league.get("sim_period_days") or 1) * WAIVER_PERIODS
    ahead = _game_days_ahead(conn, season_id)
    return ahead[days - 1] if len(ahead) >= days else None


def place(
    conn, league: dict, season_id: str, player_id: str, team_id: str, today: str
) -> dict:
    """Put a just-released player on waivers. Returns {"clears_on"}."""
    when = clears_on(conn, league, season_id)
    WaiverRepository(conn).place(league["id"], player_id, team_id, today, when)
    return {"clears_on": when}


def clears_text(waiver: dict) -> str:
    if waiver.get("clears_on"):
        return f"Clears after the games on {waiver['clears_on']}"
    return "Clears when this phase ends"


def on_waivers(conn, player_id: str) -> dict | None:
    return WaiverRepository(conn).open_for_player(player_id)


def claim_check(
    conn, league_id: str, team_id: str, player_id: str, year: int
) -> tuple[dict, dict | None, str | None]:
    """(waiver, his deal, why the team can't have him or None)."""
    waiver = on_waivers(conn, player_id)
    if waiver is None or waiver["league_id"] != league_id:
        raise WaiverError("He isn't on waivers.")
    if waiver["from_team_id"] == team_id:
        raise WaiverError("You released him.")
    deal = ContractRepository(conn).released_deal(player_id, waiver["from_team_id"])
    return waiver, deal, _why_not(conn, league_id, team_id, deal, year)


def _salary_now(deal: dict | None, year: int) -> int:
    if not deal or deal["start_year"] + deal["years"] <= year:
        return 0
    return deal["salary"]


def _why_not(conn, league_id: str, team_id: str, deal, year: int) -> str | None:
    minors = len(PlayerStatusRepository(conn).get_by_team_and_status(team_id, "minors"))
    if minors >= MINORS_LIMIT:
        return f"Your minors are full ({MINORS_LIMIT}). Release someone first."
    # Mid-season only the rest of the season is paid (src/league/prorate.py).
    added = round(_salary_now(deal, year) * prorate.still_to_pay(conn, league_id))
    return BudgetRepository(conn).refusal(league_id, team_id, year, added)


def deal_view(deal: dict | None, year: int) -> dict:
    """His deal as the claiming team would take it on."""
    if not deal:
        return {"salary_text": None, "years_left": 0, "through": None}
    left = max(0, deal["start_year"] + deal["years"] - year)
    return {
        "salary": deal["salary"],
        "salary_text": ct.format_salary(deal["salary"]),
        "years_left": left,
        "through": deal["start_year"] + deal["years"] - 1,
    }


def claim(conn, league_id: str, team_id: str, player_id: str, year: int) -> dict:
    waiver, deal, why = claim_check(conn, league_id, team_id, player_id, year)
    if why:
        raise WaiverError(why)
    WaiverRepository(conn).claim(waiver["id"], team_id)
    return {"clears_text": clears_text(waiver), **deal_view(deal, year)}


def claim_preview(
    conn, league_id: str, team_id: str, player_id: str, year: int
) -> dict:
    """For the claim confirm: his deal, when he clears, and whether the
    team could take him."""
    waiver, deal, why = claim_check(conn, league_id, team_id, player_id, year)
    return {
        "clears_text": clears_text(waiver),
        "blocked": why,
        **deal_view(deal, year),
    }


def withdraw(conn, league_id: str, team_id: str, player_id: str) -> None:
    waiver = on_waivers(conn, player_id)
    if waiver and waiver["league_id"] == league_id:
        WaiverRepository(conn).withdraw(waiver["id"], team_id)


# ── Clearing ──────────────────────────────────────────────────────────────────


def _records(conn, league_id: str, season_id: str) -> dict[str, float]:
    """Each team's win share this season, or last season's before any games
    are played. Lower is worse, and claims first."""

    def shares(sid):
        rows = conn.execute(
            """SELECT tgs.team_id, SUM(tgs.win) AS w, SUM(tgs.loss) AS l
               FROM team_game_stats tgs JOIN games g ON g.id = tgs.game_id
               WHERE g.season_id = %s AND g.series_id IS NULL AND g.completed = 1
               GROUP BY tgs.team_id""",
            (sid,),
        ).fetchall()
        return {
            r["team_id"]: r["w"] / (r["w"] + r["l"]) for r in rows if r["w"] + r["l"]
        }

    now = shares(season_id)
    if now:
        return now
    prev = conn.execute(
        """SELECT s.id FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s
             AND s.year < (SELECT year FROM seasons WHERE id = %s)
           ORDER BY s.year DESC LIMIT 1""",
        (league_id, season_id),
    ).fetchone()
    return shares(prev["id"]) if prev else {}


def claim_order(conn, league_id: str, season_id: str, waiver: dict) -> list[str]:
    """The claiming teams, worst record first (ties drawn by lot)."""
    teams = WaiverRepository(conn).claimants(waiver["id"])
    records = _records(conn, league_id, season_id)
    rng = random.Random(f"waiver:{waiver['id']}")
    draw = {t: rng.random() for t in sorted(teams)}
    return sorted(teams, key=lambda t: (records.get(t, 0.5), draw[t]))


def clear(
    conn,
    league_id: str,
    season_id: str,
    year: int,
    waiver: dict,
    on: str | None = None,
) -> str | None:
    """He clears waivers: the first claimer in order who can still fit him
    gets him. Returns that team, or None (he's a free agent). ``on``: the
    day, for the news (the last day played when None)."""
    repo = WaiverRepository(conn)
    pid = waiver["player_id"]
    order = claim_order(conn, league_id, season_id, waiver)
    player = PlayerRepository(conn).look_up(pid)
    for team_id in order:
        deal = ContractRepository(conn).released_deal(pid, waiver["from_team_id"])
        if _why_not(conn, league_id, team_id, deal, year):
            continue
        claimed = ContractRepository(conn).claim(pid, waiver["from_team_id"], team_id)
        TeamRepository(conn).add_player(team_id, pid)
        # Mid-season, the team that let him go keeps his salary for the
        # season played so far (src/league/prorate.py).
        if claimed and claimed["guaranteed"]:
            prorate.changed_teams(
                conn, league_id, pid, waiver["from_team_id"], team_id,
                claimed["salary"], year, "claim",
            )  # fmt: skip
        PlayerStatusRepository(conn).set_status(pid, "minors")
        repo.close(waiver["id"], team_id)
        if player:
            move_news.claimed(
                conn,
                league_id,
                season_id,
                player,
                waiver["from_team_id"],
                team_id,
                deal,
                len(order),
                year,
                on,
            )
        _ai_call_up(conn, league_id, season_id, team_id, on)
        return team_id
    repo.close(waiver["id"], None)
    if player:
        move_news.cleared(
            conn, league_id, season_id, player, waiver["from_team_id"], on
        )
    return None


def _ai_call_up(conn, league_id: str, season_id: str, team_id: str, on) -> None:
    """An AI team that claimed him mid-season re-picks its rosters, so the
    hole he was claimed to fill gets him from the next game (as an AI
    signing does) instead of leaving him in the minors. A person's team
    moves him up by hand; off game days the offseason sets rosters."""
    if not on or team_id in GMRepository(conn).get_human_team_ids(league_id):
        return
    outlook = front_office.outlooks(conn, league_id, season_id, on).get(team_id)
    effective = (date.fromisoformat(on) + timedelta(days=1)).isoformat()
    front_office.replan_roster(conn, league_id, season_id, team_id, outlook, effective)


def _year(conn, league_id: str) -> int | None:
    return ContractRepository(conn).current_year(league_id)


def after_day(conn, league_id: str, game_date: str) -> int:
    """After a day's games: clear the waivers due. Returns how many."""
    due = WaiverRepository(conn).due(league_id, game_date)
    return _clear_all(conn, league_id, due, game_date)


def clear_all(conn, league_id: str) -> int:
    """A phase is over: clear everyone still on waivers."""
    return _clear_all(conn, league_id, WaiverRepository(conn).open_for(league_id))


def _clear_all(conn, league_id: str, waivers: list[dict], on: str | None = None) -> int:
    if not waivers:
        return 0
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    year = _year(conn, league_id)
    if not season_id or year is None:
        return 0
    for w in waivers:
        clear(conn, league_id, season_id, year, w, on)
    return len(waivers)
