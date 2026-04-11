# src/league/season_resolver.py
import argparse
from pathlib import Path

from src.db.connection import get_connection


def get_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", "-i", required=False, help="Set the season ID.")
    return parser.parse_args()


def resolve_season(season_arg: str | None) -> tuple[str, str]:
    """
    Return season_id, auto-selecting if only one season exists.

    db_file - the file name of the db file.
    season_arg - search criteria based on year, name or id

    returns:
    - season_id - an id in the DB
    - season_label - name year combo for the season

    """

    conn = get_connection()
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
                return (s["id"], f"{s['name']} ({s['year']})")
        print(f"Season '{season_arg}' not found. Available:")
        for s in seasons:
            print(f"  id={s['id']}  year={s['year']}  name={s['name']}")
        raise SystemExit(1)

    if len(seasons) == 1:
        return (
            seasons[0]["id"],
            f"{seasons[0]['name']} ({seasons[0]['year']})",
        )

    print("Multiple seasons found — use --id to specify:")
    for s in seasons:
        print(f"  id={s['id']}  year={s['year']}  name={s['name']}")
    raise SystemExit(1)


if __name__ == "__main__":
    args = get_args()
    season_id = resolve_season(args.id)
    print(season_id)
