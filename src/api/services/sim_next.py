# src/api/services/sim_next.py
#
# Plays the next unplayed day of games for a league.
# Wraps play_game() from play_season.py, replacing the CLI args
# object with a simple config dataclass.

from __future__ import annotations

import random
import sqlite3
from dataclasses import dataclass

from src.db.repositories.games_repo import GameRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.league.play_season import play_game
from src.league.offseason.build_season_stats import build_season


@dataclass
class SimConfig:
    """Drop-in replacement for the argparse namespace play_game() expects."""

    logs: bool = False
    force: bool = False
    seed: int | None = None


def sim_next_day(league_id: str, conn: sqlite3.Connection) -> dict:
    """
    Find the next unplayed game date for this league and play all games
    scheduled on that date.

    Returns a summary dict with date, games played, and results.
    """
    league = conn.execute("SELECT * FROM leagues WHERE id = ?", (league_id,)).fetchone()
    if not league:
        raise ValueError(f"League {league_id} not found.")

    if league["state"] not in ("preseason", "season", "playoffs"):
        raise ValueError(f"League is in state '{league['state']}' — cannot sim.")

    # Find the current season for this league
    season_id = conn.execute(
        """
        SELECT season_id FROM league_seasons
        WHERE league_id = ?
        ORDER BY rowid DESC LIMIT 1
        """,
        (league_id,),
    ).fetchone()
    if not season_id:
        raise ValueError("No season found for this league.")
    season_id = season_id["season_id"]

    # Find next unplayed date
    next_date_row = conn.execute(
        """
        SELECT game_date FROM games
        WHERE season_id = ? AND completed = 0
        ORDER BY game_date ASC
        LIMIT 1
        """,
        (season_id,),
    ).fetchone()

    if not next_date_row:
        # No more regular season games — set up playoffs if not already done
        existing_series = conn.execute(
            "SELECT COUNT(*) FROM series WHERE season_id = ?",
            (season_id,),
        ).fetchone()[0]

        if existing_series == 0:
            # Auto-seed and build playoff bracket
            try:
                from src.league.playoffs.setup_playoffs import get_top_8, build_bracket
                from datetime import date, timedelta

                last_game = conn.execute(
                    """SELECT MAX(game_date) as d FROM games
                       WHERE season_id = ? AND completed = 1""",
                    (season_id,),
                ).fetchone()
                playoff_start = (
                    date.fromisoformat(last_game["d"]) + timedelta(days=5)
                    if last_game and last_game["d"]
                    else date.today()
                )
                seeds = get_top_8(conn, season_id)
                build_bracket(conn, season_id, seeds, playoff_start)
            except Exception as e:
                import traceback

                try:
                    conn.rollback()
                except Exception:
                    pass
                print(f"Playoff setup failed: {e}")
                print(traceback.format_exc())

        conn.execute("UPDATE leagues SET state = 'playoffs' WHERE id = ?", (league_id,))
        conn.commit()
        return {
            "game_date": None,
            "games_played": 0,
            "league_state": "playoffs",
            "message": "Regular season complete — playoffs ready.",
        }

    game_date = next_date_row["game_date"]

    # Load all games on this date
    games = conn.execute(
        """
        SELECT id as game_id, home_team_id, away_team_id, completed,
               season_id, game_date
        FROM games
        WHERE season_id = ? AND game_date = ? AND completed = 0
        """,
        (season_id, game_date),
    ).fetchall()

    if not games:
        return {"game_date": game_date, "games_played": 0, "results": []}

    # After loading games, build a name map for the teams involved
    team_ids = set()
    for g in games:
        team_ids.add(g["home_team_id"])
        team_ids.add(g["away_team_id"])

    placeholders = ",".join("?" * len(team_ids))
    name_rows = conn.execute(
        f"SELECT id, city, mascot FROM teams WHERE id IN ({placeholders})",
        list(team_ids),
    ).fetchall()
    team_names = {r["id"]: f"{r['city']} {r['mascot']}" for r in name_rows}

    # Advance league state to 'season' if still in preseason
    if league["state"] == "preseason":
        conn.execute("UPDATE leagues SET state = 'season' WHERE id = ?", (league_id,))
        conn.commit()

    # Set up repos
    args = SimConfig()
    seed = random.randint(0, 999_999)
    rng = random.Random(seed)

    league_mode = dict(league).get("mode", "blitz") or "blitz"

    game_repo = GameRepository(conn)
    team_repo = TeamRepository(conn)
    team_game_repo = TeamGameRepository(conn)
    rotations_repo = TeamRotationsRepository(conn)

    results = []
    errors = []

    # Snapshot GM team injuries before this day to detect changes
    gm_team_id = conn.execute(
        "SELECT team_id FROM gms WHERE league_id = ? AND is_ai = 0 AND team_id IS NOT NULL LIMIT 1",
        (league_id,),
    ).fetchone()
    gm_team_id = gm_team_id["team_id"] if gm_team_id else None

    def _get_injured(team_id):
        if not team_id:
            return {}
        rows = conn.execute(
            """SELECT pi.player_id, pi.games_remaining,
                      p.first_name || ' ' || p.last_name as name
               FROM player_injuries pi
               JOIN players p ON p.id = pi.player_id
               JOIN team_players tp ON tp.player_id = pi.player_id AND tp.team_id = ?
               WHERE pi.games_remaining > 0 AND (pi.league_id = ? OR pi.league_id = '')""",
            (team_id, league_id),
        ).fetchall()
        return {
            r["player_id"]: {"name": r["name"], "days": r["games_remaining"]}
            for r in rows
        }

    injured_before = _get_injured(gm_team_id)

    for game_info in games:
        game_dict = dict(game_info)
        try:
            result = play_game(
                conn=conn,
                args=args,
                team_repo=team_repo,
                game_repo=game_repo,
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
            import traceback

            # Rollback any dirty transaction so the next game starts clean
            try:
                conn.rollback()
            except Exception:
                pass
            errors.append(
                {
                    "game_id": game_dict["game_id"],
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
            print(f"Game {game_dict['game_id']} failed: {e}")

    # Rollup game stats into player_season_stats after each day
    if results:
        try:
            build_season(conn, season_id)
        except Exception as _bs_err:
            try:
                conn.rollback()
            except Exception:
                pass
            print(f"build_season non-fatal error (will retry next day): {_bs_err}")

    # Diff injuries to find new injuries and returns for GM's team
    injured_after = _get_injured(gm_team_id)
    new_injuries = [
        {"name": v["name"], "days": v["days"]}
        for pid, v in injured_after.items()
        if pid not in injured_before
    ]
    returned = [
        {"name": v["name"]}
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
