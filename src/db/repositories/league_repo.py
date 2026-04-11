# src/db/repositories/league_repo.py
import uuid


class LeagueRepository:
    """
    Repository for managing leagues, seasons, and team assignments.

    Typical workflow:
    1. create_league() - Create or get existing league
    2. assign_season_to_league() - Link season to league
    3. assign_to_league() - Add teams to league for that season
    """

    def __init__(self, conn):
        self.conn = conn

    def create_league(self, name: str) -> str:
        """
        Create a league or return existing league ID if name already exists.

        Args:
            name: League name (e.g., "MLB", "Minor League A")

        Returns:
            League ID (UUID hex string)
        """
        # Check if league already exists
        existing = self._get_league_id_by_name(name)
        if existing:
            return existing

        # Create new league
        league_id = uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO leagues (id, name) VALUES (%s, %s)", (league_id, name)
        )
        self.conn.commit()
        return league_id

    def _get_league_id_by_name(self, name: str) -> str | None:
        """Helper: Get league ID by name."""
        row = self.conn.execute(
            "SELECT id FROM leagues WHERE name = %s", (name,)
        ).fetchone()

        return row["id"] if row else None

    def assign_season_to_league(self, league_id: str, season_id: str) -> None:
        """
        Register a season as part of a league.
        Idempotent - safe to call multiple times.

        Args:
            league_id: League ID
            season_id: Season ID
        """
        self.conn.execute(
            """
            INSERT INTO league_seasons (league_id, season_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (league_id, season_id),
        )
        self.conn.commit()

    def assign_to_league(self, league_id: str, season_id: str, team_id: str) -> None:
        """
        Assign a team to a league for a specific season.
        Idempotent - safe to call multiple times.

        Args:
            league_id: League ID
            season_id: Season ID
            team_id: Team ID

        Note:
            Must call assign_season_to_league() first to satisfy foreign key constraint.
        """
        self.conn.execute(
            """
            INSERT INTO league_season_teams (league_id, season_id, team_id)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (league_id, season_id, team_id),
        )
        self.conn.commit()

    def has_season(self, league_id: str, season_id: str) -> bool:
        """
        Check if a season is assigned to a league.

        Args:
            league_id: League ID
            season_id: Season ID

        Returns:
            True if season is assigned to league, False otherwise
        """
        row = self.conn.execute(
            """
            SELECT 1 FROM league_seasons
            WHERE league_id = %s AND season_id = %s
            """,
            (league_id, season_id),
        ).fetchone()

        return row is not None

    def get_league_teams(self, league_id: str, season_id: str) -> list[str]:
        """
        Get all team IDs in a league for a specific season.

        Args:
            league_id: League ID
            season_id: Season ID

        Returns:
            List of team IDs
        """
        rows = self.conn.execute(
            """
            SELECT team_id FROM league_season_teams
            WHERE league_id = %s AND season_id = %s
            ORDER BY team_id
            """,
            (league_id, season_id),
        ).fetchall()

        return [row["team_id"] for row in rows]
