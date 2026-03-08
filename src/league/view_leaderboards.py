# scripts/view_leaderboards.py
import argparse
import logging
from pathlib import Path
import sqlite3

from src.league.season_resolver import resolve_season
from src.stats.analyzer import StatsAnalyzer
from src.stats.loader import StatsLoader
from src.util.logger import setup_logger


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", "-i", required=False, help="Set the season ID.")
    parser.add_argument(
        "--file", "-f", default="league.db", help="Set the league db filename."
    )
    parser.add_argument(
        "--number", "-n", type=int, default=10, help="Number of leaders to show."
    )
    parser.add_argument("--logs", action="store_true", help="Write output to log file.")
    return parser.parse_args()


def log_print(msg: str = "", logger: logging.Logger = None):
    print(msg)
    if logger:
        logger.info(msg)


def calculate_min_pa(
    db_path: Path, season_id: str, logger: logging.Logger = None
) -> tuple[float, float]:
    """Calculate minimum PA and IP for leaderboard qualification based on games completed."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    cursor = conn.execute(
        """
        SELECT COUNT(DISTINCT team_id) as num_teams
        FROM league_season_teams
        WHERE season_id = ?
        """,
        (season_id,),
    )
    num_teams = cursor.fetchone()["num_teams"]

    cursor = conn.execute(
        """
        SELECT COUNT(*) as games_completed
        FROM games
        WHERE season_id = ? AND completed = 1
        """,
        (season_id,),
    )
    games_completed = cursor.fetchone()["games_completed"]
    conn.close()

    games_per_team = (games_completed * 2) / num_teams
    min_pa = games_per_team * 3.1
    min_ip = games_per_team * 1.0

    log_print(
        f"\n📊 Qualification threshold: {min_pa:.0f} PA, {min_ip:.0f} IP ({games_per_team:.0f} games per team)",
        logger=logger,
    )

    return min_pa, min_ip


def show_all_leaderboards(
    players, top_n=10, min_pa=100, min_ip=10, logger: logging.Logger = None
):
    """Show all major leaderboards"""
    analyzer = StatsAnalyzer(players)
    min_ab = int(min_pa * 0.9)

    # === BATTING ===
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append(" BATTING STATISTICS ".center(60, "="))
    lines.append("=" * 60)
    output = "\n".join(lines)
    log_print(output, logger=logger)

    analyzer.print_leaderboard(
        "HOME RUN LEADERS",
        analyzer.leaderboard_home_runs(min_at_bats=min_ab),
        "home_runs",
        top_n=top_n,
        format_str="d",
        logger=logger,
    )
    analyzer.print_leaderboard(
        "RBI LEADERS",
        analyzer.leaderboard_rbi(min_at_bats=min_ab),
        "rbi",
        top_n=top_n,
        format_str="d",
        logger=logger,
    )
    analyzer.print_leaderboard(
        "BATTING AVERAGE LEADERS",
        analyzer.leaderboard_batting_average(min_at_bats=min_ab),
        "avg",
        top_n=top_n,
        format_str=".3f",
        logger=logger,
    )
    analyzer.print_leaderboard(
        "ON-BASE PERCENTAGE LEADERS",
        analyzer.leaderboard_on_base_percentage(min_plate_appearances=min_pa),
        "obp",
        top_n=top_n,
        format_str=".3f",
        logger=logger,
    )
    analyzer.print_leaderboard(
        "OPS LEADERS",
        analyzer.leaderboard_ops(min_at_bats=min_ab),
        "ops",
        top_n=top_n,
        format_str=".3f",
        logger=logger,
    )

    # === PITCHING ===
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append(" PITCHING STATISTICS ".center(60, "="))
    lines.append("=" * 60)
    output = "\n".join(lines)
    log_print(output, logger=logger)

    analyzer.print_leaderboard(
        "WIN LEADERS",
        analyzer.leaderboard_wins(min_innings=min_ip),
        "wins",
        top_n=top_n,
        format_str="d",
        logger=logger,
    )
    analyzer.print_leaderboard(
        "SAVE LEADERS",
        analyzer.leaderboard_saves(min_innings=0),
        "saves",
        top_n=top_n,
        format_str="d",
        logger=logger,
    )
    analyzer.print_leaderboard(
        "INNINGS PITCHED LEADERS",
        analyzer.leaderboard_innings_pitched(min_innings=min_ip),
        "innings_pitched",
        top_n=top_n,
        format_str=".1f",
        logger=logger,
    )
    analyzer.print_leaderboard(
        "ERA LEADERS (Lower is Better)",
        analyzer.leaderboard_era(min_innings=min_ip),
        "era",
        top_n=top_n,
        format_str=".2f",
        logger=logger,
    )
    analyzer.print_leaderboard(
        "STRIKEOUT LEADERS",
        analyzer.leaderboard_pitch_strikeouts(min_innings=min_ip),
        "strike_outs",
        top_n=top_n,
        format_str="d",
        logger=logger,
    )
    analyzer.print_leaderboard(
        "WALK LEADERS (Higher is worse)",
        analyzer.leaderboard_pitch_walks(min_innings=0),
        "walks",
        top_n=top_n,
        format_str="d",
        logger=logger,
    )
    analyzer.print_leaderboard(
        "WHIP LEADERS (Lower is Better)",
        analyzer.leaderboard_whip(min_innings=min_ip),
        "whip",
        top_n=top_n,
        format_str=".2f",
        logger=logger,
    )

    # === FIELDING ===
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append(" FIELDING STATISTICS ".center(60, "="))
    lines.append("=" * 60)
    output = "\n".join(lines)
    log_print(output, logger=logger)


if __name__ == "__main__":
    args = get_args()
    db_path, season_id, _ = resolve_season(args.file, args.id)

    logger = None
    if args.logs:
        logger = setup_logger(
            name="leaderboards",
            level=logging.INFO,
            console_level=logging.WARNING,
            log_id="leaderboards",
            log_to_file=True,
        )

    min_pa, min_ip = calculate_min_pa(db_path, season_id, logger=logger)

    with StatsLoader(str(db_path)) as loader:
        all_players = loader.load_season_players_with_stats(season_id)

    show_all_leaderboards(
        all_players, top_n=args.number, min_pa=min_pa, min_ip=min_ip, logger=logger
    )
