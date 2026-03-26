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
        # No games left — advance to offseason
        conn.execute(
            "UPDATE leagues SET state = 'offseason' WHERE id = ?", (league_id,)
        )
        conn.commit()
        return {
            "game_date": None,
            "games_played": 0,
            "message": "Season complete — league advanced to offseason.",
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

    game_repo = GameRepository(conn)
    team_repo = TeamRepository(conn)
    team_game_repo = TeamGameRepository(conn)
    rotations_repo = TeamRotationsRepository(conn)

    results = []
    errors = []

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

            errors.append(
                {
                    "game_id": game_dict["game_id"],
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )

    return {
        "game_date": game_date,
        "season_id": season_id,
        "games_played": len(results),
        "errors": errors,
        "seed": seed,
        "results": results,
    }
