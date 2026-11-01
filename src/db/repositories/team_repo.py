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

    def create(self, city: str, mascot: str) -> str:
        """
        Create a new team record.
        Caller must ensure this is safe.
        """
        team_id = uuid.uuid4().hex

        self.conn.execute(
            """
            INSERT INTO teams (id, city, mascot)
            VALUES (%s, %s, %s)
            """,
            (team_id, city, mascot),
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

    def get_players_team_from_team_players(self, player_id: str) -> dict:
        row = self.conn.execute(
            "SELECT team_id FROM team_players WHERE player_id = %s",
            (player_id,),
        ).fetchone()
        return row

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

    def remove_player(self, team_id: str, player_id: str) -> None:
        """Remove a player from a team's roster."""
        self.conn.execute(
            "DELETE FROM team_players WHERE team_id = %s AND player_id = %s",
            (team_id, player_id),
        )

    # ------------------------------------------------------------
    # READ
    # ------------------------------------------------------------

    def get(self, team_id: str) -> TeamRecord | None:
        """Fetch a team by ID."""
        row = self.conn.execute(
            """
            SELECT id, city, mascot
            FROM teams
            WHERE id = %s
            """,
            (team_id,),
        ).fetchone()

        if row is None:
            return None

        # Note: self.get_roster(team_id) should also use explicit columns!
        players = self.get_roster(team_id)

        return TeamRecord(
            id=row["id"],
            city=row["city"],
            mascot=row["mascot"],
            players=tuple(players),
        )

    def get_names(self, team_ids: list[str]) -> dict[str, str]:
        """Returns a mapping of id -> 'City Mascot'"""
        # Defensive check: if the set is empty, SQL will error on "IN ()"
        if not team_ids:
            return {}
        # Convert to list to satisfy the DB driver
        params = list(team_ids)
        placeholders = ", ".join(["%s"] * len(params))
        rows = self.conn.execute(
            f"SELECT id, city, mascot FROM teams WHERE id IN ({placeholders})",
            params,
        ).fetchall()
        return {r["id"]: f"{r['city']} {r['mascot']}" for r in rows}

    def find_by_city_mascot(self, city: str, mascot: str) -> str | None:
        """Fetch a team id based on city and mascot."""
        row = self.conn.execute(
            """
            SELECT id
            FROM teams
            WHERE city = %s AND mascot = %s
            """,
            (city, mascot),
        ).fetchone()

        # Returns just the string ID, much lighter
        return row["id"] if row else None

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

    def get_for_player(self, player_id: str) -> dict | None:
        """Return {id, city, mascot} for the team a player is on, or None."""
        row = self.conn.execute(
            """SELECT t.id, t.city, t.mascot FROM teams t
               JOIN team_players tp ON tp.team_id = t.id
               WHERE tp.player_id = %s""",
            (player_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_teams_in_league_season(self, league_id: str, season_id: str) -> list[dict]:
        """Return all teams in a league/season as {id, city, mascot}, ordered by city."""
        rows = self.conn.execute(
            """SELECT DISTINCT t.id, t.city, t.mascot
               FROM teams t
               JOIN league_season_teams lst ON lst.team_id = t.id
               WHERE lst.league_id = %s AND lst.season_id = %s
               ORDER BY t.city""",
            (league_id, season_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_city_mascot(self, team_id: str) -> str:
        """
        Return City and Mascot in a formatted string based on the team_id.
        If not found, just return the team_id as a string.
        """
        r = self.conn.execute(
            "SELECT city, mascot FROM teams WHERE id = %s", (team_id,)
        ).fetchone()
        return f"{r['city']} {r['mascot']}" if r else team_id

    def get_city_and_mascot(self, team_id: str) -> dict | None:
        """Return {"city", "mascot"} for the team, or None if not found."""
        return self.conn.execute(
            "SELECT city, mascot FROM teams WHERE id = %s", (team_id,)
        ).fetchone()

    def get_name(self, team_id: str) -> str:
        """Return a name string of city + space + mascot."""
        name = self.conn.execute(
            "SELECT city || ' ' || mascot AS name FROM teams WHERE id = %s", (team_id,)
        ).fetchone()["name"]
        return name

    def get_teams_in_season(self, season_id: str) -> list[dict]:
        team_rows = self.conn.execute(
            """
            SELECT DISTINCT team_id FROM league_season_teams
            WHERE season_id = %s
            """,
            (season_id,),
        ).fetchall()
        return team_rows
