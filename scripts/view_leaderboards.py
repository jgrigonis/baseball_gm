# scripts/view_leaderboards.py
from pathlib import Path

from src.stats.analyzer import StatsAnalyzer
from src.stats.loader import StatsLoader
from src.util.locations import LEAGUE_FILES_DIR


def show_all_leaderboards(players, top_n=10):
    """Show all major leaderboards"""
    analyzer = StatsAnalyzer(players)

    # === BATTING ===
    print("\n" + "=" * 60)
    print(" BATTING STATISTICS ".center(60, "="))
    print("=" * 60)

    analyzer.print_leaderboard(
        "HOME RUN LEADERS",
        analyzer.leaderboard_home_runs(min_at_bats=10),
        "home_runs",
        top_n=top_n,
        format_str="d",
    )

    analyzer.print_leaderboard(
        "RBI LEADERS",
        analyzer.leaderboard_rbi(min_at_bats=10),
        "rbi",
        top_n=top_n,
        format_str="d",
    )

    analyzer.print_leaderboard(
        "BATTING AVERAGE LEADERS",
        analyzer.leaderboard_batting_average(min_at_bats=20),
        "avg",
        top_n=top_n,
        format_str=".3f",
    )

    analyzer.print_leaderboard(
        "ON-BASE PERCENTAGE LEADERS",
        analyzer.leaderboard_on_base_percentage(min_plate_appearances=20),
        "obp",
        top_n=top_n,
        format_str=".3f",
    )

    analyzer.print_leaderboard(
        "OPS LEADERS",
        analyzer.leaderboard_ops(min_at_bats=20),
        "ops",
        top_n=top_n,
        format_str=".3f",
    )

    # === PITCHING ===
    print("\n" + "=" * 60)
    print(" PITCHING STATISTICS ".center(60, "="))
    print("=" * 60)

    # analyzer.print_leaderboard(
    #     "WINS LEADERS",
    #     analyzer.leaderboard_wins(min_innings=5),
    #     'wins',
    #     top_n=top_n,
    #     format_str='d'
    # )

    analyzer.print_leaderboard(
        "ERA LEADERS (Lower is Better)",
        analyzer.leaderboard_era(min_innings=5),
        "era",
        top_n=top_n,
        format_str=".2f",
    )

    analyzer.print_leaderboard(
        "STRIKEOUT LEADERS",
        analyzer.leaderboard_strikeouts(min_innings=5),
        "strike_outs",
        top_n=top_n,
        format_str="d",
    )

    analyzer.print_leaderboard(
        "WHIP LEADERS (Lower is Better)",
        analyzer.leaderboard_whip(min_innings=5),
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


# Usage:
if __name__ == "__main__":
    db_path = Path(LEAGUE_FILES_DIR) / "league.db"
    season_id = "b6672e1cf63f4efe8a564113d2de98fb"
    # Get all players from your games/season
    with StatsLoader(str(db_path)) as loader:
        all_players = loader.load_season_players_with_stats(season_id)
    # all_players = []  # Load your players here

    show_all_leaderboards(all_players, top_n=10)
