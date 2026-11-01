# src/league/bootstrap.py
import random

from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.io.team_importer import TeamImporter
from src.team.team_record import TeamRecord


class LeagueBootstrapper:
    def __init__(self, conn, rng: random.Random):
        self.conn = conn
        self.rng = rng or random.Random()
        self.league_repo = LeagueRepository(conn)
        self.season_repo = SeasonRepository(conn)
        self.team_importer = TeamImporter(conn, rng=self.rng)

    def bootstrap(
        self,
        teams: list[TeamRecord],
        *,
        league_id: str,
        year: int,
        season_name: str = "Season 1",
    ) -> tuple[str, list[TeamRecord], str]:
        """
        Give an existing league its first season and save its freshly
        generated teams (TeamFactory) into it.

        Returns:
            (league_id, teams with their new ids, season_id)
        """
        if not self.league_repo._get_league_id_by_id(league_id):
            raise ValueError(f"League {league_id} not found in database.")

        season_id = self.season_repo.create_season(name=season_name, year=year)
        self.league_repo.assign_season_to_league(league_id, season_id)

        saved = []
        for team in teams:
            team = self.team_importer.import_team(
                team, league_id=league_id, season_id=season_id
            )
            self.league_repo.assign_team_to_league(league_id, season_id, team.id)
            saved.append(team)

        self.conn.commit()
        return league_id, saved, season_id
