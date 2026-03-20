# src/league/play_season.py
"""
Play games in a season.
"""

import argparse
from datetime import datetime
import logging
import random
import traceback


from src.db.connection import get_connection
from src.db.repositories import bullpen_roles_repo
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.pitcher_state import PitcherStateRepository
from src.db.repositories.player_energy import PlayerEnergyRepository
from src.db.repositories.player_games import PlayerGameRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.game.game import Game
from src.team.team_in_game import TeamInGame
from src.util.logger import setup_logger


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
    parser.add_argument(
        "--logs", action="store_true", help="Keep logfiles for each game"
    )
    return parser.parse_args()


def clear_game_data(conn, game_id: str):
    """Clear all data for a game (for replaying)."""
    conn.execute("DELETE FROM player_game_stats WHERE game_id = ?", (game_id,))
    conn.execute("DELETE FROM team_game_stats WHERE game_id = ?", (game_id,))
    conn.execute("DELETE FROM player_game_fielding WHERE game_id = ?", (game_id,))
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
    conn.execute("DELETE FROM player_game_fielding WHERE game_id = ?", (game_id,))
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
                fielding_positions = list(player.fielding_by_position.items())
                for position, fs in fielding_positions:
                    if position is None:
                        raise ValueError(
                            f"Cannot insert fielding stats for player {player.id}: position is None"
                        )

                player_repo.insert(
                    game_id=game_id,
                    player_id=player.id,
                    team_id=team.record.id,
                    opponent_team_id=opponent_team.record.id,
                    stats=player.game_stats,
                    fielding_positions=fielding_positions,
                )

    conn.commit()


def load_energy(
    conn, game_repo, game_id: str, home_team: TeamInGame, away_team: TeamInGame
):
    """
    Load the pitcher energy for both teams.
    """
    pitcher_repo = PitcherStateRepository(conn)

    game_record = game_repo.get(game_id)
    game_date = datetime.fromisoformat(game_record["game_date"]).date()
    # game_date = game_record["game_date"]  # This is the date from the games table
    for player in home_team.players + away_team.players:
        state = pitcher_repo.get_with_recovery(
            player_id=player.id,
            game_date=game_date,  # From the game record
            recovery_skill=player.skills["recovery"],
        )
        if player.pitcher_fatigue:
            player.pitcher_fatigue.set_energy(state.current_energy)
    return game_date


def save_energy(conn, game_date, home_team: TeamInGame, away_team: TeamInGame):
    """
    Save the pitcher energy to the database.
    """
    pitcher_repo = PitcherStateRepository(conn)
    for player in home_team.players + away_team.players:
        if player.game_stats.pitching.pitch_count > 0:
            pitcher_repo.update_after_game(
                player_id=player.id,
                final_energy=player.pitcher_fatigue.energy,
                pitch_count=player.game_stats.pitching.pitch_count,
                game_date=game_date,  # Same date from the game record
            )


def save_position_energy(conn, player_energy_states: dict) -> None:
    repo = PlayerEnergyRepository(conn)
    for state in player_energy_states.values():
        if state.season_games_played > 0 or state.last_game_date is not None:
            repo.save(state)


def play_game(
    conn,
    args,
    team_repo: TeamRepository,
    game_repo: GameRepository,
    team_game_repo: TeamGameRepository,
    rotations_repo: TeamRotationsRepository,
    season_id: str,
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

    # load pitcher energy, game_date is the date of the current game
    game_date = load_energy(conn, game_repo, game_info["game_id"], home_team, away_team)

    # Get pitching rotations
    home_rotation = rotations_repo.get_current_rotation(
        home_team.record.id, season_id, game_date
    )
    away_rotation = rotations_repo.get_current_rotation(
        away_team.record.id, season_id, game_date
    )

    # Mark rotation pitchers
    home_rotation_ids = {r["player_id"] for r in home_rotation}
    for player in home_team.players:
        if player.record.id in home_rotation_ids:
            player.is_starter = True

    away_rotation_ids = {r["player_id"] for r in away_rotation}
    for player in away_team.players:
        if player.record.id in away_rotation_ids:
            player.is_starter = True

    # Get next starters from rotation
    home_starter_id = rotations_repo.get_next_starter(
        home_team.record.id, season_id, game_date
    )
    away_starter_id = rotations_repo.get_next_starter(
        away_team.record.id, season_id, game_date
    )

    # Setup bullpen roles
    home_bullpen = bullpen_roles_repo.get_current_roles(conn, home_record.id, season_id)
    away_bullpen = bullpen_roles_repo.get_current_roles(conn, away_record.id, season_id)
    home_role_map = {entry["player_id"]: entry["role"] for entry in home_bullpen}
    away_role_map = {entry["player_id"]: entry["role"] for entry in away_bullpen}

    for player in home_team.players:
        if player.id in home_role_map:
            player.bullpen_role = home_role_map[player.id]

    for player in away_team.players:
        if player.id in away_role_map:
            player.bullpen_role = away_role_map[player.id]

    if args.logs:
        log_level = logging.INFO
        log_id = game_info["game_id"]
        log_to_file = True
    else:
        log_level = logging.WARNING
        log_id = None
        log_to_file = False

    all_player_ids = [p.id for p in home_team.players + away_team.players]
    _ps_repo = PitcherStateRepository(conn)
    pitcher_states = {pid: _ps_repo.get(pid) for pid in all_player_ids}
    energy_repo = PlayerEnergyRepository(conn)
    injury_repo = InjuryRepository(conn)
    player_energy_states = {
        p.id: energy_repo.get_with_recovery(
            p.id, game_date, durability=p.skills.get("durability", 50)
        )
        for p in home_team.position_players + away_team.position_players
    }

    for player in home_team.position_players + away_team.position_players:
        state = player_energy_states.get(player.id)
        if state and player.player_energy:
            player.player_energy.set_energy(state.current_energy)

    logger = setup_logger(
        name="game",
        # level=logging.TRACE,
        level=log_level,
        console_level=logging.WARNING,
        log_id=log_id,
        log_to_file=log_to_file,
    )

    injury_repo.tick_all(all_player_ids)

    # Load current injured set to pass into lineup/game
    injured_ids = {p_id for p_id in all_player_ids if injury_repo.is_injured(p_id)}

    # Play game
    game = Game(
        home_team=home_team,
        away_team=away_team,
        rng=rng,
        logger=logger,
        pitcher_states=pitcher_states,
        game_date=game_date,
        player_energy_states=player_energy_states,
        injured_ids=injured_ids,
    )

    # Pass starter IDs to set_lineup
    home_team.set_lineup(
        starting_pitcher_id=home_starter_id,
        dh=True,
        injured_ids=injured_ids,
    )
    away_team.set_lineup(
        starting_pitcher_id=away_starter_id,
        dh=True,
        injured_ids=injured_ids,
    )

    # DEBUG
    for team in [home_team, away_team]:
        for slot in team.lineup:
            if slot.player.is_injured:
                logger.info(
                    f"❌ INJURED PLAYER IN LINEUP: {slot.player.name} ({team.record.mascot})"
                )
                print(
                    f"❌ INJURED PLAYER IN LINEUP: {slot.player.name} ({team.record.mascot})"
                )
                raise RuntimeError(
                    f"❌ INJURED PLAYER IN LINEUP: {slot.player.name} ({team.record.mascot})"
                )

    # Print starting pitchers and fatigue
    home_starter = next(
        (p for p in home_team.players if p.record.id == home_starter_id), None
    )
    away_starter = next(
        (p for p in away_team.players if p.record.id == away_starter_id), None
    )

    home_energy = (
        f"{home_starter.pitcher_fatigue.energy:.1f}"
        if home_starter and home_starter.pitcher_fatigue
        else "N/A"
    )
    away_energy = (
        f"{away_starter.pitcher_fatigue.energy:.1f}"
        if away_starter and away_starter.pitcher_fatigue
        else "N/A"
    )

    print(
        f"  ⚾ {away_team.record.mascot} ({away_starter.record.last_name if away_starter else '?'}, energy={away_energy})"
        f" @ {home_team.record.mascot} ({home_starter.record.last_name if home_starter else '?'}, energy={home_energy})"
    )

    logger.info(home_team.output_lineup_ratings())
    logger.info(home_team.output_pitcher_ratings())
    logger.info(away_team.output_lineup_ratings())
    logger.info(away_team.output_pitcher_ratings())

    logger.info(home_team.output_lineup_skills())
    logger.info(home_team.output_pitcher_skills())
    logger.info(away_team.output_lineup_skills())
    logger.info(away_team.output_pitcher_skills())

    logger.info(home_team.output_lineup_card())
    logger.info(away_team.output_lineup_card())

    logger.info(home_team.output_rotation_card())
    logger.info(away_team.output_rotation_card())

    logger.info(home_team.output_bullpen_card())
    logger.info(away_team.output_bullpen_card())

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

    save_energy(conn, game_date, home_team, away_team)
    save_position_energy(conn, player_energy_states)

    # Save any new injuries that occurred during the game
    for player_id, severity in game.new_injuries:
        injury_repo.injure(player_id, severity=severity, rng=rng)

    logger.info(home_team.output_defensive_stats())
    logger.info(away_team.output_defensive_stats())

    logger.info(home_team.output_batting_stats())
    logger.info(away_team.output_batting_stats())

    logger.info(home_team.output_pitching_stats())
    logger.info(away_team.output_pitching_stats())

    return result


def head_to_head_wins(conn, season_id: str, team_ids: list[str]) -> dict[str, int]:
    """
    For a group of tied teams, count wins only in games against each other.
    Returns {team_id: h2h_win_count}.
    """
    placeholders = ",".join("?" * len(team_ids))
    rows = conn.execute(
        f"""
        SELECT winner_id, COUNT(*) as wins
        FROM games
        WHERE season_id = ?
          AND completed = 1
          AND home_team_id IN ({placeholders})
          AND away_team_id IN ({placeholders})
          AND winner_id IS NOT NULL
        GROUP BY winner_id
        """,
        [season_id] + team_ids + team_ids,
    ).fetchall()

    result = {tid: 0 for tid in team_ids}
    for row in rows:
        if row["winner_id"] in result:
            result[row["winner_id"]] = row["wins"]
    return result


def sort_standings(conn, season_id: str, rows: list) -> list:
    from itertools import groupby

    # Group rows by win_pct
    sorted_rows = sorted(rows, key=lambda r: -r["win_pct"])
    result = []

    for _, group in groupby(sorted_rows, key=lambda r: r["win_pct"]):
        group = list(group)
        if len(group) == 1:
            result.extend(group)
            continue

        # Break tie with head-to-head
        tied_ids = [r["team_id"] for r in group]
        h2h = head_to_head_wins(conn, season_id, tied_ids)
        group.sort(key=lambda r: (-h2h.get(r["team_id"], 0), -r["runs_scored"]))
        result.extend(group)

    return result


def print_standings(conn, season_id: str, logger: logging.Logger = None):
    """Print current season standings."""
    rows = conn.execute(
        """
        SELECT 
            t.id as team_id,
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
        """,  # No ORDER BY — sort_standings handles this
        (season_id,),
    ).fetchall()

    sorted_rows = sort_standings(conn, season_id, [dict(r) for r in rows])

    lines = []
    lines.append("\n" + "=" * 60)
    lines.append(f"{'TEAM':<30} {'W':>5} {'L':>5} {'PCT':>7} {'RS':>6}")
    lines.append("=" * 60)
    for row in sorted_rows:
        lines.append(
            f"{row['team_name']:<30} {row['wins']:>5} {row['losses']:>5} {row['win_pct']:>7.3f} {row['runs_scored']:>6}"
        )
    lines.append("=" * 60)

    output = "\n".join(lines)
    logger.info(output)


def main():
    args = get_args()
    start_time = datetime.now()

    # Connect to database
    conn = get_connection(args.db)

    season_logger = setup_logger(
        name="season",
        level=logging.INFO,
        console_level=logging.WARNING,  # still prints to console via print()
        log_id="season",
        log_to_file=True,
    )

    # Initialize repositories
    game_repo = GameRepository(conn)
    team_repo = TeamRepository(conn)
    team_game_repo = TeamGameRepository(conn)
    rotations_repo = TeamRotationsRepository(conn)

    # Get all games for season
    games = game_repo.get_season_games(
        season_id=args.season_id, incomplete_only=args.resume, regular_season_only=True
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
    seed = args.seed if args.seed is not None else random.randint(0, 999999)
    season_logger.info(f"🎲 Seed: {seed}")
    season_logger.info(f"season id: {args.season_id}")
    rng = random.Random(seed)

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
                conn,
                args,
                team_repo,
                game_repo,
                team_game_repo,
                rotations_repo,
                args.season_id,
                game_info,
                rng,
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
                if args.logs:
                    season_logger.info(
                        f"[{i}/{len(games)}] ✅ {completed} games completed ({rate:.1f} games/sec, ~{remaining:.0f}s remaining)"
                    )
            else:
                if args.logs:
                    season_logger.info(f"[{i}/{len(games)}] ✅ {result}")
                print(f"[{i}/{len(games)}] ✅ {result}")

        except Exception as e:
            print(
                f"[{i}/{len(games)}] ❌ Error playing game {game_info['game_id']}: {e}"
            )
            print(traceback.format_exc())

            continue

    # Final stats
    elapsed = (datetime.now() - start_time).total_seconds()
    msg_complete = f"✅ Season complete! Games played: {completed}, Time: {elapsed:.1f}s ({completed/elapsed:.2f} games/sec)"
    print("\n" + msg_complete)
    season_logger.info(msg_complete)

    # Print standings
    print_standings(conn, args.season_id, season_logger)


if __name__ == "__main__":
    main()
