# src/league/statistics/print_standings.py
import argparse
import logging
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


def head_to_head_wins(conn, season_id: str, team_ids: list[str]) -> dict[str, int]:
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

    sorted_rows = sorted(rows, key=lambda r: -r["win_pct"])
    result = []

    for _, group in groupby(sorted_rows, key=lambda r: r["win_pct"]):
        group = list(group)
        if len(group) == 1:
            result.extend(group)
            continue

        tied_ids = [r["team_id"] for r in group]
        h2h = head_to_head_wins(conn, season_id, tied_ids)
        group.sort(key=lambda r: (-h2h.get(r["team_id"], 0), -r["runs_scored"]))
        result.extend(group)

    return result


def print_standings(db_path: Path, season_id: str, logger: logging.Logger = None):
    conn = get_connection(db_path)

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
        WHERE g.season_id = ? AND g.completed = 1 AND g.series_id IS NULL
        GROUP BY t.id
        """,  # No ORDER BY — sort_standings handles this
        (season_id,),
    ).fetchall()

    sorted_rows = sort_standings(conn, season_id, [dict(r) for r in rows])

    # print("\n" + "=" * 60)
    # print(f"{'TEAM':<30} {'W':>5} {'L':>5} {'PCT':>7} {'RS':>6}")
    # print("=" * 60)
    # for row in sorted_rows:
    #     print(f"{row['team_name']:<30} {row['wins']:>5} {row['losses']:>5} {row['win_pct']:>7.3f} {row['runs_scored']:>6}")
    # print("=" * 60 + "\n")

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
    if logger:
        logger.info(output)
    else:
        print(output)

def main():
    args = parse_args()
    db_path, season_id, _ = resolve_season(args.file, args.id)
    print_standings(db_path, season_id)


if __name__ == "__main__":
    main()
