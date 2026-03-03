# src/league/season_resolver.py
import argparse
from pathlib import Path
import sqlite3

from src.util.locations import LEAGUE_FILES_DIR


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", "-i", required=False, help="Set the season ID.")
    parser.add_argument(
        "--file", "-f", default="league.db", help="Set the league db filename."
    )
    return parser.parse_args()


def resolve_season(db_file: str, season_arg: str | None) -> tuple[str, str, str]:
    """
    Return season_id, auto-selecting if only one season exists.

    db_file - the file name of the db file.
    season_arg - search criteria based on year, name or id

    returns:
    - db_path - a Path to the db file
    - season_id - an id in the DB
    - season_label - name year combo for the season

    """
    db_path = Path(LEAGUE_FILES_DIR) / db_file
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
            if (
                str(s["year"]) == season_arg
                or s["name"] == season_arg
                or s["id"] == season_arg
            ):
                return (db_path, s["id"], f"{s['name']} ({s['year']})")
        print(f"Season '{season_arg}' not found. Available:")
        for s in seasons:
            print(f"  id={s['id']}  year={s['year']}  name={s['name']}")
        raise SystemExit(1)

    if len(seasons) == 1:
        return (
            db_path,
            seasons[0]["id"],
            f"{seasons[0]['name']} ({seasons[0]['year']})",
        )

    print("Multiple seasons found — use --id to specify:")
    for s in seasons:
        print(f"  id={s['id']}  year={s['year']}  name={s['name']}")
    raise SystemExit(1)


if __name__ == "__main__":
    args = get_args()
    db_path, season_id = resolve_season(args.file, args.id)
    print(season_id)
