# scripts/show_season_stats.py
# (season-specific version)
from pathlib import Path
from src.stats.loader import StatsLoader
from src.stats.analyzer import StatsAnalyzer
from src.util.locations import LEAGUE_FILES_DIR


def main():
    db_path = Path(LEAGUE_FILES_DIR) / "league.db"
    season_id = "b6672e1cf63f4efe8a564113d2de98fb"  # Or whatever your season ID is

    with StatsLoader(str(db_path)) as loader:
        # Get players for specific season
        season_players = loader.load_season_players_with_stats(season_id)

        print(f"2026 Season Leaders ({len(season_players)} players)\n")

        analyzer = StatsAnalyzer(season_players)

    # Show leaderboards
    print("\n" + "=" * 60)
    print("HOME RUN LEADERS")
    print("=" * 60)
    hr_leaders = analyzer.leaderboard_home_runs(min_at_bats=20)
    for i, leader in enumerate(hr_leaders[:10], 1):
        p = leader["player"].record  # Access the PlayerRecord
        print(
            f"{i:2d}. {p.name:30s} {leader['home_runs']:3d} HR "
            f"({leader['at_bats']} AB)"
        )

    print("\n" + "=" * 60)
    print("BATTING AVERAGE LEADERS (min 20 AB)")
    print("=" * 60)
    avg_leaders = analyzer.leaderboard_batting_average(min_at_bats=20)
    for i, leader in enumerate(avg_leaders[:10], 1):
        p = leader["player"].record
        print(
            f"{i:2d}. {p.name:30s} {leader['avg']:.3f} "
            f"({leader['hits']}/{leader['at_bats']})"
        )

    print("\n" + "=" * 60)
    print("ERA LEADERS (min 5 IP)")
    print("=" * 60)
    era_leaders = analyzer.leaderboard_era(min_innings=5.0)
    for i, leader in enumerate(era_leaders[:10], 1):
        p = leader["player"].record
        print(
            f"{i:2d}. {p.name:30s} {leader['era']:.2f} ERA "
            f"({leader['innings']:.1f} IP)"
        )


if __name__ == "__main__":
    main()
