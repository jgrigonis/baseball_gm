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

from src.db.repositories.games_repo import GameRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.playoff_repo import PlayoffRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.league.play_season import play_game
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
                try:
                    conn.rollback()
                except Exception:
                    pass
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

    # Snapshot GM team injuries before this day to detect changes
    gm_repo = GMRepository(conn)
    gm_team_id = gm_repo.get_first_human_team_id(league_id)

    inj_repo = InjuryRepository(conn, league_id)
    injured_before = inj_repo.get_active_for_team(gm_team_id)

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
            # Rollback any dirty transaction so the next game starts clean
            try:
                conn.rollback()
            except Exception:
                pass
            errors.append(
                {
                    "game_id": game_dict["game_id"],
                    "error": str(e),
                }
            )
            log.exception("Game %s failed", game_dict["game_id"])

    # Rollup game stats into player_season_stats after each day
    if results:
        try:
            build_season(conn, season_id)
        except Exception as _bs_err:
            try:
                conn.rollback()
            except Exception:
                pass
            log.warning("build_season failed, will retry next day: %s", _bs_err)

    # Diff injuries to find new injuries and returns for GM's team
    injured_after = inj_repo.get_active_for_team(gm_team_id)
    new_injuries = [
        {"name": v["name"], "days": v["days"], "is_pitcher": v["is_pitcher"]}
        for pid, v in injured_after.items()
        if pid not in injured_before
    ]
    status_repo = PlayerStatusRepository(conn)
    returned = [
        {
            "name": v["name"],
            "is_pitcher": v["is_pitcher"],
            "on_40man": status_repo.get_status(pid) in ("26man", "40man"),
        }
        for pid, v in injured_before.items()
        if pid not in injured_after
    ]

    return {
        "game_date": game_date,
        "season_id": season_id,
        "games_played": len(results),
        "errors": errors,
        "seed": seed,
        "results": results,
        "league_state": "season",
        "new_injuries": new_injuries,
        "returned": returned,
    }
