# src/league/bootstrap.py
from pathlib import Path
import random

from src.db.repositories.bullpen_roles_repo import set_roles
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.player.player_evaluator import PlayerEvaluator
from src.io.team_importer import TeamImporter


class LeagueBootstrapper:
    def __init__(self, conn, rng: random.Random):
        self.conn = conn
        self.rng = rng or random.Random()
        self.league_repo = LeagueRepository(conn)
        self.season_repo = SeasonRepository(conn)
        self.team_repo = TeamRepository(conn)
        self.team_importer = TeamImporter(conn, rng=self.rng)
        self.rotations_repo = TeamRotationsRepository(conn)
        self.status_repo = PlayerStatusRepository(conn)

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
            row = self.conn.execute(
                "SELECT id FROM leagues WHERE id = %s", (league_id,)
            ).fetchone()
            if not row:
                raise ValueError(f"League {league_id} not found in database.")
        else:
            # Old CLI path — create or look up by name as before
            league_id = self.league_repo.create_league(manifest["league_name"])
            # self.conn.commit() # Moved out of league_repo, don't think we ever get on this code path anyway

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
        # self.conn.commit() # Moved out of league_repo, may move it down further

        teams = []
        for team_def in manifest["teams"]:
            team = self.team_importer.import_csv(
                league_id=league_id,
                season_id=season_id,
                path=str(
                    Path(str(manifest.get("season_year", 2026)))
                    / league_id
                    / team_def["csv"]
                ),
                city=team_def["city"],
                mascot=team_def["mascot"],
                allow_existing=True,
                allow_roster_update=allow_roster_update,
                force_new=force_new_teams,
            )
            self.league_repo.assign_to_league(league_id, season_id, team.id)
            teams.append(team)

        # Set starting rotations for all teams
        self._bootstrap_rotations(teams, season_id, start_date)

        self.conn.commit()  # Moved out of league_repo
        return league_id, teams, season_id

    def _bootstrap_rotations(self, teams, season_id: str, start_date: str) -> None:
        """Set the initial starting rotation for each team using 26-man roster only."""
        for team in teams:
            # Filter to 26-man players only
            active_ids = set(self.status_repo.get_by_team_and_status(team.id, "26man"))
            active_players = [p for p in team.players if p.id in active_ids]

            # Inline rotation selection — avoid dataclasses.replace on slots=True frozen dataclass
            pitchers = [p for p in active_players if p.is_pitcher()]
            pitchers.sort(
                key=lambda p: PlayerEvaluator.rate_player(p.skills).get("sp", 0),
                reverse=True,
            )
            rotation = [p.id for p in pitchers[:5]]
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
            # Initialise the rotation pointer at sp1 so game 1 always starts correctly
            self.conn.execute(
                """INSERT INTO team_rotation_pointer
                       (team_id, season_id, series_id, next_order, updated_at)
                   VALUES (%s, %s, '', 1, NOW())
                   ON CONFLICT (team_id, season_id, series_id) DO UPDATE
                       SET next_order = 1, updated_at = NOW()""",
                (team.id, season_id),
            )
            self._bootstrap_bullpen(
                team, active_players, rotation, season_id, start_date
            )
            self.conn.commit()

    def _bootstrap_bullpen(
        self, team, active_players, rotation, season_id: str, start_date: str
    ) -> None:
        relievers = [
            p for p in active_players if p.is_pitcher() and p.id not in set(rotation)
        ]
        roles = team.set_bullpen_roles(rotation, relievers=relievers)
        if not roles:
            print(
                f"Warning: No pitchers found for team {team.name}, skipping bullpen roles."
            )
        set_roles(self.conn, team.id, season_id, roles, start_date)
