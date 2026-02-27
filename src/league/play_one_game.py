# src/league/play_one_game.py
"""
Play a single game and store results.
"""

import argparse
import random
import sqlite3
from pathlib import Path

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
    parser.add_argument("--game-id", "-i", required=True, help="Game ID to play")
    parser.add_argument(
        "--seed", "-s", type=int, help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--pauses", "-p", action="store_true", help="Pause after each step"
    )
    parser.add_argument(
        "--force", "-f", action="store_true", help="Force replay of completed game"
    )
    return parser.parse_args()


def save_player_stats(conn, game_id: str, home_team: TeamInGame, away_team: TeamInGame):
    """Save player game stats to database."""
    # Clear existing stats if replaying
    conn.execute("DELETE FROM player_game_stats WHERE game_id = ?", (game_id,))
    conn.commit()

    player_repo = PlayerGameRepository(conn)
    saved_count = 0

    # Save home team stats
    for player in home_team.players:
        # Only save if player participated
        if (
            player.game_stats.batting.plate_appearances > 0
            or player.game_stats.pitching.pitch_count > 0
            or player.game_stats.fielding.chances > 0
        ):

            player_repo.insert(
                game_id=game_id,
                player_id=player.id,
                team_id=home_team.record.id,
                opponent_team_id=away_team.record.id,
                stats=player.game_stats,
            )
            saved_count += 1

    # Save away team stats
    for player in away_team.players:
        if (
            player.game_stats.batting.plate_appearances > 0
            or player.game_stats.pitching.pitch_count > 0
            or player.game_stats.fielding.chances > 0
        ):

            player_repo.insert(
                game_id=game_id,
                player_id=player.id,
                team_id=away_team.record.id,
                opponent_team_id=home_team.record.id,
                stats=player.game_stats,
            )
            saved_count += 1

    print(f"✅ Saved stats for {saved_count} players")


def print_player_stats(home_team: TeamInGame, away_team: TeamInGame):
    """Save player game stats to database."""
    # Just print stats
    print("\n📊 HOME TEAM STATS:")
    for player in home_team.players:
        if player.game_stats.batting.plate_appearances > 0:
            print(
                f"  {player.name}: {player.game_stats.batting.hits}-{player.game_stats.batting.at_bats}"
            )

    print("\n📊 AWAY TEAM STATS:")
    for player in away_team.players:
        if player.game_stats.batting.plate_appearances > 0:
            print(
                f"  {player.name}: {player.game_stats.batting.hits}-{player.game_stats.batting.at_bats}"
            )


def main():
    args = get_args()

    # Connect to database
    conn = sqlite3.connect(Path(LEAGUE_FILES_DIR) / args.db)
    conn.row_factory = sqlite3.Row

    game_repo = GameRepository(conn)
    team_game_repo = TeamGameRepository(conn)

    # Load game
    game_info = game_repo.get(args.game_id)

    # Check if already completed
    if game_info.get("completed") and not args.force:
        print(f"❌ Game {args.game_id} already completed!")
        print(
            f"   Score: {game_info['away_team_id']} {game_info['away_score']} @ {game_info['home_team_id']} {game_info['home_score']}"
        )
        print("   Use --force to replay")
        return

    if game_info.get("completed") and args.force:
        print("⚠️  Replaying completed game (--force)")
        # Clear existing data
        conn.execute("DELETE FROM player_game_stats WHERE game_id = ?", (args.game_id,))
        conn.execute("DELETE FROM team_game_stats WHERE game_id = ?", (args.game_id,))
        conn.commit()

    print(f"🎮 Loading game: {args.game_id}")
    print(f"   Season: {game_info['season_id']}")
    print(f"   Date: {game_info['game_date']}")

    # Load teams
    team_repo = TeamRepository(conn)
    home_record = team_repo.get(game_info["home_team_id"])
    away_record = team_repo.get(game_info["away_team_id"])

    if not home_record or not away_record:
        raise ValueError("Could not load team records")

    print(
        f"   {away_record.city} {away_record.mascot} @ {home_record.city} {home_record.mascot}"
    )

    # Create teams in game
    home_team = TeamInGame(home_record)
    away_team = TeamInGame(away_record)

    # For now, use default lineup from roster order
    home_team.set_lineup()
    away_team.set_lineup()

    # Create and play game
    rng = random.Random(args.seed) if args.seed else random.Random()
    game = Game(home_team=home_team, away_team=away_team, rng=rng, pauses=args.pauses)

    result = game.play()

    # Determine winner
    winner_id = (
        game_info["home_team_id"]
        if result.home_score > result.away_score
        else game_info["away_team_id"]
    )
    # Save results
    game_repo.save_result(args.game_id, result, winner_id)
    team_game_repo.save_game_stats(
        args.game_id,
        game_info["home_team_id"],
        game_info["away_team_id"],
        home_team,
        away_team,
        result.home_score,
        result.away_score,
    )
    save_player_stats(conn, args.game_id, home_team, away_team)
    print_player_stats(home_team, away_team)

    print("\n✅ Game complete and saved!")


# if __name__ == "__main__":
#     main()

# This script is deprecated, needs similar updates that are found in play_season.py
