# src/league/bootstrap.py
import random

from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.io.team_importer import TeamImporter
from src.league.league_constants import LEAGUE_START_YEAR


class LeagueBootstrapper:
    def __init__(self, conn, rng: random.Random):
        self.conn = conn
        self.rng = rng or random.Random()
        self.league_repo = LeagueRepository(conn)
        self.season_repo = SeasonRepository(conn)
        self.team_repo = TeamRepository(conn)
        self.team_importer = TeamImporter(conn, rng=self.rng)

    def bootstrap_from_manifest(
        self,
        manifest,
        start_date,
        allow_roster_update=False,
        league_id: str | None = None,
        force_new_teams=False,
    ):
        """
        Bootstrap a league from a manifest.

        Args:
            manifest: League manifest dict
            start_date: Season start date
            allow_roster_update: If True, re-import updated CSVs
            league_id: If provided, use this existing league ID instead of
                       creating or looking up by name. This prevents duplicate
                       league rows when called from the API.

        Returns:
            (league_id, teams, season_id)
        """
        if league_id is not None:
            # Use the provided ID — skip create_league entirely
            # Verify it exists
            row = self.league_repo._get_league_id_by_id(league_id)
            if not row:
                raise ValueError(f"League {league_id} not found in database.")
        else:
            # Old CLI path — create or look up by name as before
            league_id = self.league_repo.create_league(manifest["league_name"])

        # Defaults to name=Season1 year=LEAGUE_START_YEAR if not in the manifest
        season_id = self.season_repo.create_season(
            name=manifest.get("season_name", "Season1"),
            year=manifest.get("season_year", LEAGUE_START_YEAR),
        )

        # Check if this league-season combo already exists
        if self.league_repo.has_season(league_id, season_id):
            teams = self.team_repo.get_teams_by_season(season_id)
            # Already bootstrapped, return early
            return league_id, teams, season_id

        # Link the season to the league
        self.league_repo.assign_season_to_league(league_id, season_id)
        # self.conn.commit() # Moved out of league_repo, may move it down further

        teams = []
        for team_def in manifest["teams"]:
            team = self.team_importer.import_csv(
                league_id=league_id,
                season_id=season_id,
                year=str(manifest.get("season_year", LEAGUE_START_YEAR)),
                csv_file=team_def["csv"],
                city=team_def["city"],
                mascot=team_def["mascot"],
                allow_existing=True,
                allow_roster_update=allow_roster_update,
                force_new=force_new_teams,
            )
            self.league_repo.assign_team_to_league(league_id, season_id, team.id)
            teams.append(team)

        self.conn.commit()  # Moved out of league_repo
        return league_id, teams, season_id
