# scripts/check_info.py
import argparse
import sqlite3
from pathlib import Path


def get_args():
    """
    Get arguments from the command line.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--path",
        "-p",
        default="leagues/league.db",
        help="Set the path to the database file.",
    )
    parser.add_argument(
        "--name",
        "-n",
        default="JAMES WELLS",
        help="Set the name of the player to check.",
    )
    args = parser.parse_args()
    return args


def main(args):
    db_path = Path(args.path)
    if not db_path.exists():
        print(f"Database file not found: {db_path}")
        return
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    check_info(conn, args.name)
    conn.close()


def check_info(conn, name):
    """
    Check the info for a specific player.
    """
    try:
        first_name, last_name = (part.upper() for part in name.split())
    except ValueError:
        print(f"Invalid name: {name}")
        print("Name must be in the format 'First Last'")
        return

    cursor = conn.execute(
        """
        SELECT COUNT(*) as total_games
        FROM games g
        JOIN team_players tp ON (g.home_team_id = tp.team_id OR g.away_team_id = tp.team_id)
        JOIN players p ON tp.player_id = p.id
        WHERE p.first_name = ? AND p.last_name = ?
        AND g.completed = 1
    """,
        (first_name, last_name),
    )
    print("Team's total games:", cursor.fetchone()["total_games"])

    cursor = conn.execute(
        """
        SELECT ps.*
        FROM player_skills ps
        JOIN players p ON ps.player_id = p.id
        WHERE p.first_name = ? AND p.last_name = ?
    """,
        (first_name, last_name),
    )
    try:
        print(f"\n{name.upper()}'s skills:", dict(cursor.fetchone()))
    except TypeError:
        print(f"No skills found for {name.upper()}")
        return


if __name__ == "__main__":
    args = get_args()
    main(args)
