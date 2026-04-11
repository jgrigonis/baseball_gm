# src/db/repositories/team_repo.py
"""
Handles:

Team identity
Career metadata
Lookups
Not stats.
Insert player information
Know how to persist teams
Know how to associate teams
Know how to answer safety questions

NOT create domain Team objects
"""

import uuid

from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills
from src.team.team_record import TeamRecord


class TeamRepository:
    def __init__(self, conn):
        self.conn = conn

    # ------------------------------------------------------------
    # TEAM CREATION
    # ------------------------------------------------------------

    def create(
        self,
        city: str,
        mascot: str,
        *,
        source_csv: str | None = None,
        source_hash: str | None = None,
    ) -> str:
        """
        Create a new team record.
        Caller must ensure this is safe.
        """
        team_id = uuid.uuid4().hex

        self.conn.execute(
            """
            INSERT INTO teams (
                id, city, mascot, source_csv, source_hash
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (team_id, city, mascot, source_csv, source_hash),
        )

        return team_id

    def add_to_league(self, league_id: str, season_id: str, team_id: str):
        """
        Attach a team to a league for a specific season.
        Idempotent.
        """
        self.conn.execute(
            """
            INSERT INTO league_season_teams (league_id, season_id, team_id)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (league_id, season_id, team_id),
        )

    # ------------------------------------------------------------
    # WRITE
    # ------------------------------------------------------------

    def add_player(self, team_id: str, player_id: str):
        """
        Add player to team roster.
        Idempotent.
        """
        self.conn.execute(
            """
            INSERT INTO team_players (team_id, player_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (team_id, player_id),
        )

    def get(self, team_id: str) -> TeamRecord | None:
        """
        Fetch a team by ID.
        """
        row = self.conn.execute(
            """
            SELECT *
            FROM teams
            WHERE id = %s
            """,
            (team_id,),
        ).fetchone()

        if row is None:
            return None

        players = self.get_roster(team_id)

        return TeamRecord(
            id=row["id"],
            city=row["city"],
            mascot=row["mascot"],
            source_csv=row["source_csv"],
            source_hash=row["source_hash"],
            players=tuple(players),
        )

    def find_by_city_mascot(self, city: str, mascot: str) -> str | None:
        """
        Fetch a team id based on city and mascot
        """
        row = self.conn.execute(
            """
            SELECT *
            FROM teams
            WHERE city = %s AND mascot = %s
            """,
            (city, mascot),
        ).fetchone()

        if row is None:
            return None

        return row["id"]

    def is_in_league(self, team_id: str, league_id: str, season_id: str) -> bool:
        """Check if team is in a specific league for a specific season"""
        row = self.conn.execute(
            """
            SELECT 1
            FROM league_season_teams
            WHERE league_id = %s AND season_id = %s AND team_id = %s
            """,
            (league_id, season_id, team_id),
        ).fetchone()

        return row is not None

    def has_players(self, team_id: str) -> bool:
        row = self.conn.execute(
            """
            SELECT 1
            FROM team_players
            WHERE team_id = %s
            LIMIT 1
            """,
            (team_id,),
        ).fetchone()

        return row is not None

    def load_for_game(self, team_id: str) -> TeamRecord:
        team_row = self.get(team_id)
        players = self.get_roster(team_id)

        return TeamRecord.from_records(team_row, players)

    def get_roster(self, team_id: str) -> list[PlayerRecord]:
        """
        Get all players on a team's roster with current skills.
        Returns empty list if team has no players.
        """
        rows = self.conn.execute(
            """
            SELECT 
                p.id, p.first_name, p.last_name, p.bats, p.throws, p.position,
                ps.age, ps.clutch, ps.speed, ps.power, ps.eye, ps.contact,
                ps.base_running, ps.bunting, ps.catching, ps.infield, ps.outfield,
                ps.arm, ps.accuracy, ps.stamina, ps.recovery, ps.ground_balls, ps.strikes
            FROM players p
            JOIN team_players tp ON p.id = tp.player_id
            JOIN player_skills ps ON p.id = ps.player_id
            WHERE tp.team_id = %s
            """,
            (team_id,),
        ).fetchall()

        return [
            PlayerRecord(
                id=row["id"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                bats=row["bats"],
                throws=row["throws"],
                position=row["position"],
                skills=PlayerSkills.from_db_row(row),
            )
            for row in rows
        ]

    def get_teams_by_season(self, season_id: str) -> list[TeamRecord]:
        """Get all teams in a season."""
        cursor = self.conn.execute(
            """
            SELECT t.id FROM teams t
            JOIN league_season_teams lst ON t.id = lst.team_id
            WHERE lst.season_id = %s
            """,
            (season_id,),
        )
        team_ids = [row["id"] for row in cursor.fetchall()]
        return [self.get(team_id) for team_id in team_ids]

    def remove_player(self, team_id: str, player_id: str) -> None:
        """Remove a player from a team's roster."""
        self.conn.execute(
            "DELETE FROM team_players WHERE team_id = %s AND player_id = %s",
            (team_id, player_id),
        )
        self.conn.commit()
