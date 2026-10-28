# src/api/services/ai_trades.py
#
# AI teams starting trades (plans/trades.md, section 7). Runs from the sim
# after a day's games, every RUN_EVERY_DAYS days, and every day in the
# DEADLINE_RUSH_DAYS before the trade deadline.
#
# Each run, each AI team gets a chance to look for a deal. Its team state
# (src/api/services/team_states.py) decides how it judges one, and how keen it
# is: once the standings have had their say, buyers (all-in, contending) and
# sellers (rebuilding, aging out) look more often (ACT_CHANCE); everyone else,
# and everyone early in the season, rarely. It looks at a few other teams (PARTNERS_PER_LOOK) and keeps the
# best deal it finds (src/league/trades/ai_proposer.py):
#   - with a team a person runs, it makes an offer, which pops up for them
#     and waits for their answer: until after EXPIRES_AFTER_DAYS league days
#     in single player, or the end of the next period in multiplayer. Offers
#     read as news, not spam: a GM gets one open AI offer at a time, waits
#     DAYS_BETWEEN_OFFERS for the next (fewer in the rush), and gets
#     MAX_AI_OFFERS_A_SEASON a season, only MAX_AI_OFFERS_BEFORE_RUSH of them
#     before the rush.
#   - with another AI team, both have already agreed, so it goes through at
#     once. Only a buyer or a seller starts one, once the standings have had
#     their say. They're rare: one a season for each AI team
#     (MAX_AI_TRADES_A_SEASON), one for every TEAMS_PER_AI_TRADE teams in the
#     league, most of them saved for the rush (SHARE_OF_AI_TRADES_BEFORE_RUSH),
#     and AI_TRADES_PER_RUN a run (more in the rush), so AI teams move players
#     without building super-teams.
#
# Everything is seeded from the league and the date, so a run is the same
# every time it's replayed.

from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta

from src.api.services import team_states, trades
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.ready_check_repo import ReadyCheckRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.trade_repo import TradeRepository
from src.league import trade_deadline
from src.league.team_state import BUYERS, SELLERS
from src.league.trades import ai_evaluator
from src.league.trades.ai_proposer import Side, find_deal

RUN_EVERY_DAYS = 3
DEADLINE_RUSH_DAYS = 14
ACT_CHANCE = {"buyer": 0.3, "seller": 0.3, "other": 0.08}
RUSH_ACT_CHANCE = {"buyer": 0.5, "seller": 0.5, "other": 0.12}
PARTNERS_PER_LOOK = 4
EXPIRES_AFTER_DAYS = 3
DAYS_BETWEEN_OFFERS = 10
RUSH_DAYS_BETWEEN_OFFERS = 3
MAX_AI_OFFERS_A_SEASON = 6
MAX_AI_OFFERS_BEFORE_RUSH = 3
MAX_AI_TRADES_A_SEASON = 1
TEAMS_PER_AI_TRADE = 6
SHARE_OF_AI_TRADES_BEFORE_RUSH = 0.25
AI_TRADES_PER_RUN = 1
RUSH_AI_TRADES_PER_RUN = 2


def after_day(conn, league_id: str, game_date: str) -> dict:
    """After a day's games: expire single-player offers whose time is up,
    then, if it's a day the AI looks, let AI teams make offers and trades.
    Run under the league lock. Returns {"offers": n, "trades": n}."""
    league = LeagueRepository(conn).get_by_id(league_id)
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    if not league or not season_id:
        return {"offers": 0, "trades": 0}
    league = dict(league)
    trades.close_due_on(conn, league_id, game_date)
    window = trade_deadline.window(conn, league, season_id)
    if not window["open"] or not _looks_today(game_date, window["deadline"]):
        return {"offers": 0, "trades": 0}
    return run(conn, league, season_id, game_date, window["deadline"])


def _rush(game_date: str, deadline: str | None) -> bool:
    if not deadline:
        return False
    days = (date.fromisoformat(deadline) - date.fromisoformat(game_date)).days
    return 0 <= days <= DEADLINE_RUSH_DAYS


def _looks_today(game_date: str, deadline: str | None) -> bool:
    return _rush(game_date, deadline) or (
        date.fromisoformat(game_date).toordinal() % RUN_EVERY_DAYS == 0
    )


def run(conn, league: dict, season_id: str, game_date: str, deadline) -> dict:
    """One look by every AI team. Returns how many offers and trades it made."""
    league_id = league["id"]
    rng = random.Random(_seed(league_id, game_date))
    rush = _rush(game_date, deadline)
    chance = RUSH_ACT_CHANCE if rush else ACT_CHANCE
    trades_left = RUSH_AI_TRADES_PER_RUN if rush else AI_TRADES_PER_RUN

    teams = [
        t["id"]
        for t in TeamRepository(conn).get_teams_in_league_season(league_id, season_id)
    ]
    humans = set(GMRepository(conn).get_human_team_ids(league_id))
    ai_teams = [t for t in teams if t not in humans]
    rows = team_states.current(conn, league_id, season_id, game_date)
    states = {t: rows[t]["state"] for t in teams}
    roles = {t: _role(rows[t]) for t in teams}
    days_left = trades._days_left(conn, season_id, game_date)
    trade_repo = TradeRepository(conn)
    ai_made = trade_repo.ai_trades_this_season(season_id)
    trades_left = min(trades_left, league_ai_trades(len(teams), rush) - ai_made["all"])

    def can_trade(t):
        return trades_left > 0 and ai_made.get(t, 0) < MAX_AI_TRADES_A_SEASON

    def can_offer_to(t):
        return _can_offer_to(trade_repo, league_id, season_id, t, game_date, rush)

    actors = [t for t in ai_teams if rng.random() < chance[roles[t]]]
    if not actors:
        return {"offers": 0, "trades": 0}
    sides = _sides(conn, league_id, teams, states, game_date)

    offers = made = 0
    for team_id in actors:
        partners = [
            t
            for t in teams
            if t != team_id
            and (
                can_offer_to(t)
                if t in humans
                else roles[team_id] != "other" and can_trade(t) and can_trade(team_id)
            )
        ]
        rng.shuffle(partners)
        best = None
        for partner in partners[:PARTNERS_PER_LOOK]:
            me = sides[team_id]
            them = sides[partner]
            if partner in humans:
                # A person decides: offer what would make their team better,
                # with no margin of their own.
                them = Side(them.team_id, them.state, them.roster, them.tradeable, 0.0)
            # Don't make a GM the same offer twice.
            avoid = (
                trade_repo.ai_offers_made(season_id, team_id, partner)
                if partner in humans
                else set()
            )
            deal = find_deal(me, them, days_left, avoid)
            if deal and (best is None or deal.score > best[1].score):
                best = (partner, deal)
        if not best:
            continue
        partner, deal = best
        give = [a.id for a in deal.give]
        get = [a.id for a in deal.get]
        try:
            trades._check_assets(conn, league, season_id, team_id, partner, give, get)
        except trades.TradeError:
            continue
        if partner in humans:
            if not can_offer_to(partner):
                continue
            _offer(conn, league, season_id, team_id, partner, give, get, game_date)
            offers += 1
        else:
            trades.ai_trade(
                conn, league_id, season_id, team_id, partner, give, get, game_date
            )
            made += 1
            trades_left -= 1
            for t in (team_id, partner, "all"):
                ai_made[t] = ai_made.get(t, 0) + 1
            # Their rosters changed: look at them afresh next run.
            sides.update(_sides(conn, league_id, [team_id, partner], states, game_date))
    conn.commit()
    return {"offers": offers, "trades": made}


def league_ai_trades(team_count: int, rush: bool) -> int:
    """How many trades between AI teams a league has room for in a season,
    and how many of them before the rush."""
    cap = max(1, team_count // TEAMS_PER_AI_TRADE)
    if rush:
        return cap
    return max(1, round(cap * SHARE_OF_AI_TRADES_BEFORE_RUSH))


def _role(row: dict) -> str:
    """buyer, seller or other: what a team's state means for how keen it is
    to deal. Everyone's other until the standings have had their say."""
    if not team_states.in_race(row):
        return "other"
    if row["state"] in BUYERS:
        return "buyer"
    if row["state"] in SELLERS:
        return "seller"
    return "other"


def _sides(conn, league_id, team_ids, states, game_date) -> dict[str, Side]:
    injuries = InjuryRepository(conn, league_id)
    statuses = _statuses(conn, team_ids)
    out = {}
    for t in team_ids:
        hurt = injuries.get_team_injuries(t, game_date)
        roster = trades._assets(conn, t, hurt)
        out[t] = Side(
            team_id=t,
            state=states[t],
            roster=roster,
            tradeable={a.id for a in roster if statuses.get(a.id) in trades.TRADEABLE},
            margin=ai_evaluator.margin(t, "offer", game_date),
        )
    return out


def _statuses(conn, team_ids) -> dict[str, str]:
    rows = conn.execute(
        """SELECT tp.player_id, s.status FROM team_players tp
           JOIN player_status s ON s.player_id = tp.player_id
           WHERE tp.team_id = ANY(%s)""",
        (list(team_ids),),
    ).fetchall()
    return {r["player_id"]: r["status"] for r in rows}


def _can_offer_to(trade_repo, league_id, season_id, team_id, today, rush) -> bool:
    """A GM gets one open AI offer at a time, spaced out, and a few a
    season, most of them saved for the rush."""
    if trade_repo.open_ai_offers_to(league_id, team_id):
        return False
    cap = MAX_AI_OFFERS_A_SEASON if rush else MAX_AI_OFFERS_BEFORE_RUSH
    if trade_repo.ai_offers_to_this_season(season_id, team_id) >= cap:
        return False
    last = trade_repo.last_ai_offer_to(season_id, team_id)
    if not last:
        return True
    wait = RUSH_DAYS_BETWEEN_OFFERS if rush else DAYS_BETWEEN_OFFERS
    return (date.fromisoformat(today) - date.fromisoformat(last)).days >= wait


def _offer(conn, league, season_id, from_team, to_team, give, get, game_date):
    multiplayer = ReadyCheckRepository(conn).human_gm_count(league["id"]) > 1
    if multiplayer:
        period = ReadyCheckRepository(conn).period(league["id"])["sim_period"]
        expiry = {"expires_period": period + 1}
    else:
        until = date.fromisoformat(game_date) + timedelta(days=EXPIRES_AFTER_DAYS)
        expiry = {"expires_on": until.isoformat()}
    trades.ai_offer(
        conn, league["id"], season_id, from_team, to_team, give, get, game_date, expiry
    )


def _seed(league_id: str, game_date: str) -> int:
    digest = hashlib.sha256(f"ai-trades|{league_id}|{game_date}".encode()).digest()
    return int.from_bytes(digest[:8], "big")
