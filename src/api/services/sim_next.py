# src/api/services/sim_next.py
#
# Plays the next unplayed day of games for a league.
# Wraps play_game() from play_season.py, replacing the CLI args
# object with a simple config dataclass.

from __future__ import annotations


from dataclasses import dataclass
from datetime import date, timedelta
import logging
import random

import psycopg

from src.api.services import ai_trades, team_states, trades
from src.api.services.injury_news import InjuryNews
from src.db.connection import rollback_quietly
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.playoff_repo import PlayoffRepository
from src.db.repositories.ready_check_repo import ReadyCheckRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.league.play_season import play_game
from src.league import trade_deadline
from src.team.roster_limits import enforce_roster_limits
from src.league.playoffs.setup_playoffs import setup_playoff_bracket
from src.league.offseason.build_season_stats import build_season

log = logging.getLogger(__name__)


@dataclass
class SimConfig:
    """Drop-in replacement for the argparse namespace play_game() expects."""

    logs: bool = False
    force: bool = False
    seed: int | None = None


def sim_next_day(league_id: str, conn) -> dict:
    """
    Find the next unplayed game date for this league and play all games
    scheduled on that date.

    Returns a summary dict with date, games played, and results.
    """
    lr = LeagueRepository(conn)
    tr = TeamRepository(conn)
    gr = GameRepository(conn)
    por = PlayoffRepository(conn)
    league = lr.get_by_id(league_id)
    if not league:
        raise ValueError(f"League {league_id} not found.")

    if league["state"] not in ("preseason", "season", "playoffs"):
        raise ValueError(f"League is in state '{league['state']}' — cannot sim.")

    # Find the current season for this league
    season_id = SeasonRepository(conn).get_current_id_for_league(league_id)
    if not season_id:
        raise ValueError("No season found for this league.")

    # Find next unplayed date
    next_date_row = gr.get_next_unplayed_date(season_id)

    if not next_date_row:
        # No more regular season games — set up playoffs if not already done
        existing_series = por.existing_series_exist(season_id)

        if not existing_series:
            try:
                last_game = gr.last_game_date(season_id)
                playoff_start = (
                    date.fromisoformat(last_game["d"]) + timedelta(days=5)
                    if last_game and last_game["d"]
                    else date.today()
                )
                setup_playoff_bracket(conn, season_id, league_id, playoff_start)
            except Exception as e:
                rollback_quietly(conn)
                log.exception("Playoff setup failed for league %s", league_id)
                # Stay in the current state so the next sim retries the setup,
                # rather than entering the playoffs with no bracket.
                return {
                    "game_date": None,
                    "games_played": 0,
                    "league_state": league["state"],
                    "errors": [{"error": f"Playoff setup failed: {e}"}],
                    "message": "Regular season complete, but playoff setup failed.",
                }

        lr.set_state(league_id, "playoffs")

        conn.commit()
        return {
            "game_date": None,
            "games_played": 0,
            "league_state": "playoffs",
            "message": "Regular season complete — playoffs ready.",
        }

    game_date = next_date_row["game_date"]

    # Load all games on this date
    games = gr.get_days_games(season_id, game_date)

    if not games:
        return {"game_date": game_date, "games_played": 0, "results": []}

    # After loading games, build a name map for the teams involved
    team_ids = set()
    for g in games:
        team_ids.add(g["home_team_id"])
        team_ids.add(g["away_team_id"])

    team_names = tr.get_names(team_ids)

    # Advance league state to 'season' if still in preseason
    if league["state"] == "preseason":
        lr.set_state(league_id, "season")
        conn.commit()

    # Set up repos
    args = SimConfig()
    seed = random.randint(0, 999_999)
    rng = random.Random(seed)

    league_mode = dict(league).get("mode", "blitz") or "blitz"

    team_game_repo = TeamGameRepository(conn)
    rotations_repo = TeamRotationsRepository(conn, league_id)

    results = []
    errors = []

    # Rosters below the minimum or over the limit, e.g. after a trade, are
    # fixed before anyone plays.
    for team_id in team_ids:
        enforce_roster_limits(conn, league_id, team_id, league_mode)

    # Snapshot the human teams' injuries so each GM hears about changes
    injury_news = InjuryNews(conn, league_id)

    for game_info in games:
        game_dict = dict(game_info)
        try:
            result = play_game(
                conn=conn,
                args=args,
                team_repo=tr,
                game_repo=gr,
                team_game_repo=team_game_repo,
                rotations_repo=rotations_repo,
                season_id=season_id,
                game_info=game_dict,
                rng=rng,
                league_id=league_id,
                league_mode=league_mode,
            )
            results.append(
                {
                    "game_id": game_dict["game_id"],
                    "home_team_id": game_dict["home_team_id"],
                    "away_team_id": game_dict["away_team_id"],
                    "home_team": team_names.get(
                        game_dict["home_team_id"], game_dict["home_team_id"]
                    ),
                    "away_team": team_names.get(
                        game_dict["away_team_id"], game_dict["away_team_id"]
                    ),
                    "home_score": result.home_score,
                    "away_score": result.away_score,
                    "innings": result.innings_played,
                }
            )
        except Exception as e:
            # Deliberately broad: one broken game must not stop the rest of the
            # day. The game saves all-or-nothing, so rolling back discards only
            # its partial writes. The traceback is logged below.
            rollback_quietly(conn)
            errors.append(
                {
                    "game_id": game_dict["game_id"],
                    "error": str(e),
                }
            )
            log.exception("Game %s failed", game_dict["game_id"])

    if results:
        lr.mark_played(league_id)
        conn.commit()
        # Rollup game stats into player_season_stats after each day
        try:
            build_season(conn, season_id)
        except psycopg.Error:
            rollback_quietly(conn)
            log.warning("build_season failed, will retry next day", exc_info=True)

    injury_news.record()

    return {
        "game_date": game_date,
        "season_id": season_id,
        "games_played": len(results),
        "errors": errors,
        "seed": seed,
        "results": results,
        "league_state": "season",
    }


def sim_days(league_id: str, conn, count: int | str) -> dict:
    """
    Play the next ``count`` days of the regular season, or the rest of it
    when count is "season". When the season ends, sets up the playoffs.
    Stops early after the games of trade deadline day, in leagues that
    trade, so every GM gets a last look, and, in a single-player league that
    asks for it (stop_for_trade_offers), when a trade offer arrives for the
    GM. Between days, AI teams make offers and trades (ai_trades). Playing past the deadline expires every open offer first. Returns a
    summary of what was played.
    """
    season_repo = SeasonRepository(conn)
    game_repo = GameRepository(conn)

    season_id = season_repo.get_current_id_for_league(league_id)
    results = []
    remaining = game_repo.games_remaining(season_id)
    limit = remaining if count == "season" else min(int(count), remaining)

    league = LeagueRepository(conn).get_by_id(league_id)
    deadline = (
        trade_deadline.deadline_date(conn, season_id)
        if league and trade_deadline.trades_enabled_for(league["mode"])
        else None
    )
    at_deadline = False
    if deadline:
        trades.close_at_deadline(conn, league_id)
        conn.commit()
    watch_offers = bool(
        deadline
        and league["stop_for_trade_offers"]
        and ReadyCheckRepository(conn).human_gm_count(league_id) <= 1
    )
    offers_before = trades.offers_to_humans(conn, league_id) if watch_offers else set()
    new_offer = False

    for _ in range(limit):
        day_result = sim_next_day(league_id, conn)
        gp = day_result.get("games_played", 0)
        if gp > 0:
            results.append(day_result)
        # Stop if season ended (no game_date) or if state changed out of season
        if not day_result.get("game_date"):
            break
        # Stop if no games played and it wasn't a transient error
        if gp == 0 and not day_result.get("errors"):
            break
        # Front offices take stock every week or so (team states).
        if gp > 0:
            team_states.refresh_if_due(conn, league_id, day_result["game_date"])
            conn.commit()
        # AI teams make offers and trades between game days.
        if deadline and gp > 0:
            ai_trades.after_day(conn, league_id, day_result["game_date"])
        if deadline and day_result["game_date"] == deadline:
            at_deadline = True
            break
        # An offer can expire mid-sim, so look for one that's new, not for
        # more of them.
        if watch_offers and trades.offers_to_humans(conn, league_id) - offers_before:
            new_offer = True
            break

    new_remaining = game_repo.games_remaining(
        season_repo.get_current_id_for_league(league_id)
    )
    # Season over: move on to the playoffs (sets up the bracket). Also covers
    # an earlier call whose playoff setup failed and left nothing to play.
    if new_remaining == 0:
        sim_next_day(league_id, conn)

    return {
        "days_simmed": len(results),
        "games_played": sum(r.get("games_played", 0) for r in results),
        "games_remaining": new_remaining,
        "last_date": results[-1]["game_date"] if results else None,
        "trade_deadline": at_deadline,
        "trade_offer": new_offer,
    }
