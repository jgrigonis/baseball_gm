
import os
import sqlite3

from src.db.init import init_db
from src.league.bootstrap import LeagueBootstrapper
from manifest import load_manifest
from src.util.locations import LEAGUE_FILES_DIR


def main():
    conn = sqlite3.connect(LEAGUE_FILES_DIR + os.sep + "league.db")
    conn.row_factory = sqlite3.Row
    init_db(conn)

    boot = LeagueBootstrapper(conn)
    manifest = load_manifest(LEAGUE_FILES_DIR + os.sep + "league_teams.json")
    league_id, team_ids = boot.bootstrap_from_manifest(manifest)

    print(f"League created: {league_id}")
    print(f"Teams imported: {len(team_ids)}")

if __name__ == "__main__":
    main()


    
# league_id = create_league("My League")
# season_id = create_season(league_id, year=2025)

# team_importer = TeamImporter(conn)

# # 2 teams!
# # When we expand we'll probably want to iterate a list or json.
# teams = []
# home = team_importer.import_csv("Giants.csv", "San Francisco", "Giants")
# away = team_importer.import_csv("Team1.csv", "Team", "1")

# schedule = Schedule(home, away)

# for game in schedule.games:
#     GameRunner.play(game, season_id)
