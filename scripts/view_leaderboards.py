# scripts/view_leaderboards.py
import argparse
from pathlib import Path
import sqlite3

from src.stats.analyzer import StatsAnalyzer
from src.stats.loader import StatsLoader
from src.util.locations import LEAGUE_FILES_DIR


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", "-i", required=False, help="Set the season ID.")
    parser.add_argument(
        "--file", "-f", default="league.db", help="Set the league db filename."
    )
    parser.add_argument(
        "--number", "-n", type=int, default=10, help="Number of leaders to show."
    )
    return parser.parse_args()


def resolve_season(db_path: Path, season_arg: str | None) -> str:
    """Return season_id, auto-selecting if only one season exists."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT id, year, name FROM seasons ORDER BY year")
    seasons = cur.fetchall()
    conn.close()

    if not seasons:
        print("No seasons found in database.")
        raise SystemExit(1)

    if season_arg:
        for s in seasons:
            if str(s["year"]) == season_arg or s["name"] == season_arg or s["id"] == season_arg:
                return s["id"]
        print(f"Season '{season_arg}' not found. Available:")
        for s in seasons:
            print(f"  id={s['id']}  year={s['year']}  name={s['name']}")
        raise SystemExit(1)

    if len(seasons) == 1:
        return seasons[0]["id"]

    print("Multiple seasons found — use --id to specify:")
    for s in seasons:
        print(f"  id={s['id']}  year={s['year']}  name={s['name']}")
    raise SystemExit(1)


def calculate_min_pa(db_path: Path, season_id: str) -> tuple[float, float]:
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

    print(
        f"\n📊 Qualification threshold: {min_pa:.0f} PA, {min_ip:.0f} IP ({games_per_team:.0f} games per team)"
    )

    return min_pa, min_ip


def show_all_leaderboards(players, top_n=10, min_pa=100, min_ip=10):
    """Show all major leaderboards"""
    analyzer = StatsAnalyzer(players)
    min_ab = int(min_pa * 0.9)

    # === BATTING ===
    print("\n" + "=" * 60)
    print(" BATTING STATISTICS ".center(60, "="))
    print("=" * 60)

    analyzer.print_leaderboard(
        "HOME RUN LEADERS",
        analyzer.leaderboard_home_runs(min_at_bats=min_ab),
        "home_runs",
        top_n=top_n,
        format_str="d",
    )
    analyzer.print_leaderboard(
        "RBI LEADERS",
        analyzer.leaderboard_rbi(min_at_bats=min_ab),
        "rbi",
        top_n=top_n,
        format_str="d",
    )
    analyzer.print_leaderboard(
        "BATTING AVERAGE LEADERS",
        analyzer.leaderboard_batting_average(min_at_bats=min_ab),
        "avg",
        top_n=top_n,
        format_str=".3f",
    )
    analyzer.print_leaderboard(
        "ON-BASE PERCENTAGE LEADERS",
        analyzer.leaderboard_on_base_percentage(min_plate_appearances=min_pa),
        "obp",
        top_n=top_n,
        format_str=".3f",
    )
    analyzer.print_leaderboard(
        "OPS LEADERS",
        analyzer.leaderboard_ops(min_at_bats=min_ab),
        "ops",
        top_n=top_n,
        format_str=".3f",
    )

    # === PITCHING ===
    print("\n" + "=" * 60)
    print(" PITCHING STATISTICS ".center(60, "="))
    print("=" * 60)

    analyzer.print_leaderboard(
        "WIN LEADERS",
        analyzer.leaderboard_wins(min_innings=min_ip),
        "wins",
        top_n=top_n,
        format_str="d",
    )
    analyzer.print_leaderboard(
        "SAVE LEADERS",
        analyzer.leaderboard_saves(min_innings=0),
        "saves",
        top_n=top_n,
        format_str="d",
    )
    analyzer.print_leaderboard(
        "INNINGS PITCHED LEADERS",
        analyzer.leaderboard_innings_pitched(min_innings=min_ip),
        "innings_pitched",
        top_n=top_n,
        format_str=".1f",
    )
    analyzer.print_leaderboard(
        "ERA LEADERS (Lower is Better)",
        analyzer.leaderboard_era(min_innings=min_ip),
        "era",
        top_n=top_n,
        format_str=".2f",
    )
    analyzer.print_leaderboard(
        "STRIKEOUT LEADERS",
        analyzer.leaderboard_strikeouts(min_innings=min_ip),
        "strike_outs",
        top_n=top_n,
        format_str="d",
    )
    analyzer.print_leaderboard(
        "WALK LEADERS (Higher is worse)",
        analyzer.leaderboard_pitch_walks(min_innings=0),
        "walks",
        top_n=top_n,
        format_str="d",
    )
    analyzer.print_leaderboard(
        "WHIP LEADERS (Lower is Better)",
        analyzer.leaderboard_whip(min_innings=min_ip),
        "whip",
        top_n=top_n,
        format_str=".2f",
    )

    # === FIELDING ===
    print("\n" + "=" * 60)
    print(" FIELDING STATISTICS ".center(60, "="))
    print("=" * 60)

    analyzer.print_leaderboard(
        "PUTOUT LEADERS",
        analyzer.leaderboard_putouts(),
        "putouts",
        top_n=top_n,
        format_str="d",
    )
    analyzer.print_leaderboard(
        "ASSIST LEADERS",
        analyzer.leaderboard_assists(),
        "assists",
        top_n=top_n,
        format_str="d",
    )


if __name__ == "__main__":
    args = get_args()
    db_path = Path(LEAGUE_FILES_DIR) / args.file
    season_id = resolve_season(db_path, args.id)

    min_pa, min_ip = calculate_min_pa(db_path, season_id)

    with StatsLoader(str(db_path)) as loader:
        all_players = loader.load_season_players_with_stats(season_id)

    show_all_leaderboards(all_players, top_n=args.number, min_pa=min_pa, min_ip=min_ip)
