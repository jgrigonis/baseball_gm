# src/league/print_standings.py
import argparse
import sqlite3
from pathlib import Path

from src.db.connection import get_connection
from src.league.season_resolver import resolve_season


def parse_args():
    parser = argparse.ArgumentParser(
        description="League-wide stat totals for a season."
    )
    parser.add_argument(
        "--id", "-i", required=False, help="Season ID (or partial name/year match)"
    )
    parser.add_argument(
        "--file", "-f", default="league.db", help="Set the league db filename."
    )
    args = parser.parse_args()
    return args


def print_standings(db_path: Path, season_id: str):
    """Print current season standings."""
    conn = get_connection(db_path)

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
        WHERE g.season_id = ? AND g.completed = 1 AND g.series_id IS NULL
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
    args = parse_args()
    db_path, season_id, _ = resolve_season(args.file, args.id)
    print_standings(db_path, season_id)


if __name__ == "__main__":
    main()
