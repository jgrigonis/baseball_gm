from src.db.repositories.league_repo import LeagueRepository
from src.team.team_importer import TeamImporter

class LeagueBootstrapper:
    def __init__(self, conn):
        self.conn = conn
        self.league_repo = LeagueRepository(conn)
        self.team_importer = TeamImporter(conn)

    def bootstrap_from_manifest(self, manifest):
        league_id = self.league_repo.create_league(manifest["league_name"])

        team_ids = []
        for team_def in manifest["teams"]:
            team_id = self.team_importer.import_csv(
                path=team_def["csv"],
                city=team_def["city"],
                mascot=team_def["mascot"],
                # league_id=league_id,
                # csv_file=team_def["csv"],
                # city=team_def["city"],
                # mascot=team_def["mascot"],
            )
            team_ids.append(team_id)

        return league_id, team_ids
