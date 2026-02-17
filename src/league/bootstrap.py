# src/league/bootstrap.py

from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.io.team_importer import TeamImporter


class LeagueBootstrapper:
    def __init__(self, conn):
        self.conn = conn
        self.league_repo = LeagueRepository(conn)
        self.season_repo = SeasonRepository(conn)
        self.team_repo = TeamRepository(conn)
        self.team_importer = TeamImporter(conn)
        self.rotations_repo = TeamRotationsRepository(conn)

    def bootstrap_from_manifest(self, manifest, start_date):
        league_id = self.league_repo.create_league(manifest["league_name"])

        # Defaults to name=Season1 year=2026 if not found in manifest
        season_id = self.season_repo.create_season(
            name=manifest.get("season_name", "Season1"),
            year=manifest.get("season_year", 2026),
        )

        # Check if this league-season combo already exists
        if self.league_repo.has_season(league_id, season_id):
            teams = self.team_repo.get_teams_by_season(season_id)
            # Already bootstrapped, return early
            return league_id, teams, season_id

        # Link the season to the league
        self.league_repo.assign_season_to_league(league_id, season_id)

        teams = []
        for team_def in manifest["teams"]:
            team = self.team_importer.import_csv(
                league_id=league_id,
                season_id=season_id,
                path=team_def["csv"],
                city=team_def["city"],
                mascot=team_def["mascot"],
                allow_existing=True,
            )
            self.league_repo.assign_to_league(league_id, season_id, team.id)
            teams.append(team)

        # Set starting rotations for all teams
        self._bootstrap_rotations(teams, season_id, start_date)

        return league_id, teams, season_id

    def _bootstrap_rotations(self, teams, season_id: str, start_date: str) -> None:
        """Set the initial starting rotation for each team."""
        for team in teams:
            rotation = team.assign_starting_rotation()
            if not rotation:
                print(
                    f"Warning: No pitchers found for team {team.name}, skipping rotation."
                )
                continue
            self.rotations_repo.set_rotation(
                team_id=team.id,
                season_id=season_id,
                player_id_list=rotation,
                effective_date=start_date,
            )
