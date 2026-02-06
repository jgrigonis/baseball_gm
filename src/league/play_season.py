# src/league/play_season.py
"""
Play all games in a season.
"""
import argparse
import logging
import random
import sqlite3
from pathlib import Path
from datetime import datetime

from src.db.repositories.games_repo import GameRepository
from src.db.repositories.player_games import PlayerGameRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_repo import TeamRepository
from src.game.game import Game
from src.team.team_in_game import TeamInGame
from src.util.locations import LEAGUE_FILES_DIR


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", "-d", default="league.db", help="DB File Name")
    parser.add_argument("--season-id", "-i", required=True, help="Season ID to play")
    parser.add_argument(
        "--seed", "-s", type=int, help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--force", "-f", action="store_true", help="Replay completed games"
    )
    parser.add_argument("--limit", "-l", type=int, help="Limit number of games to play")
    parser.add_argument(
        "--resume", "-r", action="store_true", help="Resume from last completed game"
    )
    return parser.parse_args()


def clear_game_data(conn, game_id: str):
    """Clear all data for a game (for replaying)."""
    conn.execute("DELETE FROM player_game_stats WHERE game_id = ?", (game_id,))
    conn.execute("DELETE FROM team_game_stats WHERE game_id = ?", (game_id,))
    conn.execute(
        """
        UPDATE games 
        SET home_score = NULL, away_score = NULL, winner_id = NULL, 
            innings_played = NULL, completed = 0
        WHERE id = ?
        """,
        (game_id,),
    )
    conn.commit()


def save_game_result(conn, game_id: str, game_info: dict, result):
    """Save game result to database."""
    winner_id = (
        game_info["home_team_id"]
        if result.home_score > result.away_score
        else game_info["away_team_id"]
    )

    conn.execute(
        """
        UPDATE games 
        SET home_score = ?, away_score = ?, winner_id = ?, innings_played = ?, completed = 1
        WHERE id = ?
        """,
        (
            result.home_score,
            result.away_score,
            winner_id,
            result.innings_played,
            game_id,
        ),
    )
    conn.commit()


def save_team_stats(
    conn,
    game_id: str,
    game_info: dict,
    home_team: TeamInGame,
    away_team: TeamInGame,
    result,
):
    """Save team game stats to database."""
    conn.execute("DELETE FROM team_game_stats WHERE game_id = ?", (game_id,))

    cursor = conn.cursor()

    # Calculate team totals
    home_hits = sum(p.game_stats.batting.hits for p in home_team.players)
    away_hits = sum(p.game_stats.batting.hits for p in away_team.players)

    home_errors = sum(p.game_stats.fielding.errors for p in home_team.players)
    away_errors = sum(p.game_stats.fielding.errors for p in away_team.players)

    # Determine win/loss
    home_win = 1 if result.home_score > result.away_score else 0
    home_loss = 1 if result.home_score < result.away_score else 0
    away_win = 1 if result.away_score > result.home_score else 0
    away_loss = 1 if result.away_score < result.home_score else 0

    # Save home team stats
    cursor.execute(
        """
        INSERT INTO team_game_stats (
            game_id, team_id, runs, hits, errors, win, loss
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            game_id,
            game_info["home_team_id"],
            result.home_score,
            home_hits,
            home_errors,
            home_win,
            home_loss,
        ),
    )

    # Save away team stats
    cursor.execute(
        """
        INSERT INTO team_game_stats (
            game_id, team_id, runs, hits, errors, win, loss
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            game_id,
            game_info["away_team_id"],
            result.away_score,
            away_hits,
            away_errors,
            away_win,
            away_loss,
        ),
    )

    conn.commit()


def save_player_stats(conn, game_id: str, home_team: TeamInGame, away_team: TeamInGame):
    """Save player game stats to database."""
    conn.execute("DELETE FROM player_game_stats WHERE game_id = ?", (game_id,))
    conn.commit()

    player_repo = PlayerGameRepository(conn)

    # Save stats for both teams
    for team, opponent_team in [(home_team, away_team), (away_team, home_team)]:
        for player in team.players:
            if (
                player.game_stats.batting.plate_appearances > 0
                or player.game_stats.pitching.pitch_count > 0
                or player.game_stats.fielding.chances > 0
            ):

                player_repo.insert(
                    game_id=game_id,
                    player_id=player.id,
                    team_id=team.record.id,
                    opponent_team_id=opponent_team.record.id,
                    stats=player.game_stats,
                )

    conn.commit()


def play_game(
    conn,
    team_repo: TeamRepository,
    game_repo: GameRepository,
    team_game_repo: TeamGameRepository,
    game_info: dict,
    rng: random.Random,
):
    """Play a single game and save results."""
    # Load teams
    home_record = team_repo.get(game_info["home_team_id"])
    away_record = team_repo.get(game_info["away_team_id"])

    # Create teams in game
    home_team = TeamInGame(home_record)
    away_team = TeamInGame(away_record)

    # Set lineups
    home_team.set_lineup()
    away_team.set_lineup()

    # Play game
    game = Game(
        home_team=home_team, away_team=away_team, rng=rng, log_level=logging.WARNING
    )

    result = game.play()

    # Determine winner
    winner_id = (
        game_info["home_team_id"]
        if result.home_score > result.away_score
        else game_info["away_team_id"]
    )
    # Save results
    game_repo.save_result(game_info["game_id"], result, winner_id)
    team_game_repo.save_game_stats(
        game_info["game_id"],
        game_info["home_team_id"],
        game_info["away_team_id"],
        home_team,
        away_team,
        result.home_score,
        result.away_score,
    )
    save_player_stats(conn, game_info["game_id"], home_team, away_team)

    return result


def print_standings(conn, season_id: str):
    """Print current season standings."""
    rows = conn.execute(
        """
        SELECT 
            t.city || ' ' || t.mascot as team_name,
            SUM(tgs.win) as wins,
            SUM(tgs.loss) as losses,
            SUM(tgs.runs) as runs_scored,
            ROUND(CAST(SUM(tgs.win) AS FLOAT) / (SUM(tgs.win) + SUM(tgs.loss)), 3) as win_pct
        FROM teams t
        JOIN team_game_stats tgs ON t.id = tgs.team_id
        JOIN games g ON tgs.game_id = g.id
        WHERE g.season_id = ? AND g.completed = 1
        GROUP BY t.id
        ORDER BY win_pct DESC, wins DESC
        """,
        (season_id,),
    ).fetchall()

    print("\n" + "=" * 60)
    print(f"{'TEAM':<30} {'W':>5} {'L':>5} {'PCT':>7} {'RS':>6}")
    print("=" * 60)
    for row in rows:
        print(f"{row[0]:<30} {row[1]:>5} {row[2]:>5} {row[4]:>7.3f} {row[3]:>6}")
    print("=" * 60 + "\n")


def main():
    args = get_args()
    start_time = datetime.now()

    # Connect to database
    conn = sqlite3.connect(Path(LEAGUE_FILES_DIR) / args.db)
    conn.row_factory = sqlite3.Row

    # Initialize repositories
    game_repo = GameRepository(conn)
    team_repo = TeamRepository(conn)
    team_game_repo = TeamGameRepository(conn)

    # Get all games for season
    games = game_repo.get_season_games(
        season_id=args.season_id, incomplete_only=args.resume
    )

    if not games:
        print(f"❌ No games found for season {args.season_id}")
        if args.resume:
            print("   All games already completed! Use --force to replay.")
        return

    total_games = len(games)
    if args.limit:
        games = games[: args.limit]

    print(f"🏟️  Playing {len(games)} games for season {args.season_id}")
    if args.resume:
        print(f"   (Resuming - {total_games - len(games)} already completed)")

    # Setup RNG
    rng = random.Random(args.seed) if args.seed else random.Random()

    # Play games
    completed = 0
    for i, game_info in enumerate(games, 1):
        # Skip completed games unless force
        if game_info["completed"] and not args.force:
            print(f"[{i}/{len(games)}] Skipping completed game {game_info['game_id']}")
            continue

        # Clear data if replaying
        if game_info["completed"] and args.force:
            clear_game_data(conn, game_info["game_id"])

        try:
            result = play_game(
                conn, team_repo, game_repo, team_game_repo, game_info, rng
            )
            completed += 1

            # Print progress
            if completed % 10 == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = completed / elapsed if elapsed > 0 else 0
                remaining = (len(games) - completed) / rate if rate > 0 else 0
                print(
                    f"[{i}/{len(games)}] ✅ {completed} games completed ({rate:.1f} games/sec, ~{remaining:.0f}s remaining)"
                )
            else:
                print(f"[{i}/{len(games)}] ✅ {result}")

        except Exception as e:
            print(
                f"[{i}/{len(games)}] ❌ Error playing game {game_info['game_id']}: {e}"
            )
            continue

    # Final stats
    elapsed = (datetime.now() - start_time).total_seconds()
    print(f"\n✅ Season complete!")
    print(f"   Games played: {completed}")
    print(f"   Time: {elapsed:.1f} seconds ({completed/elapsed:.2f} games/sec)")

    # Print standings
    print_standings(conn, args.season_id)


if __name__ == "__main__":
    main()
