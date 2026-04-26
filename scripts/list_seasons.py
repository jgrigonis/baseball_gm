# scripts/list_seasons.py

from src.db.connection import get_connection
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository


l_width = 50
s_width = 48
y_width = 12
n_width = 20

def main():
    # args = parse_args()
    conn = get_connection()
    sr = SeasonRepository(conn)
    lr = LeagueRepository(conn)

    seasons = sr.get_all_seasons()
    if not seasons:
        print("No seasons found.")
        return

    for season in seasons:
        league_id = lr.get_league_id_from_season_id(season["id"])
        print(f"{'league_id: ' + str(league_id):<{l_width}} "
            f"{'season_id: ' + str(season['id']):<{s_width}} "
            f"{'year: ' + str(season['year']):<{y_width}} "
            f"{'name: ' + season['name']:<{n_width}}"
        )


if __name__ == "__main__":
    main()
