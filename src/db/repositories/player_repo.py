# src/db/repositories/player_repo.py
"""
Repository for player identity and skills management.

Handles:
- Creating and updating player records
- Managing current player skills
- Tracking skill history across seasons
- Looking up player information

Uses tables:
- players (identity)
- player_skills (current skills)
- player_skills_history (skill snapshots per season)
"""

import datetime
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills


class PlayerRepository:
    """Repository for managing player identity and skills."""

    def __init__(self, conn):
        self.conn = conn

    # ------------------------------------------------------------
    # WRITE - Identity
    # ------------------------------------------------------------

    def insert(
        self,
        id: str,
        first_name: str,
        last_name: str,
        bats: str,
        throws: str,
        position: str,
        skills: PlayerSkills,
        age: int,
    ) -> None:
        """
        Create a player record with identity and initial skills.
        Idempotent - calling multiple times updates the record.

        Args:
            id: Player ID
            first_name: Player's first name
            last_name: Player's last name
            bats: Batting hand ('L', 'R', or 'S' for switch) - case insensitive
            throws: Throwing hand ('L' or 'R') - case insensitive
            position: Primary position
            skills: PlayerSkills object with all skill ratings
            age: Player's age

        Raises:
            ValueError: If bats or throws values are invalid
        """
        # Normalize handedness to uppercase
        bats = bats.upper()
        throws = throws.upper()

        # Validate
        if bats not in ("L", "R", "S"):
            raise ValueError(f"Invalid bats value: '{bats}'. Must be L, R, or S")
        if throws not in ("L", "R"):
            raise ValueError(f"Invalid throws value: '{throws}'. Must be L or R")

        # Insert identity
        self.conn.execute(
            """
            INSERT OR REPLACE INTO players (
                id, first_name, last_name, bats, throws, position, age
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (id, first_name, last_name, bats, throws, position, age),
        )

        # Insert or update skills
        self.update_skills(id, skills)

        self.conn.commit()

    def update_skills(self, player_id: str, skills: PlayerSkills) -> None:
        """
        Update a player's current skills.
        Used for training, aging, injuries, etc.

        Args:
            player_id: Player ID
            skills: PlayerSkills object with updated ratings
        """
        skill_dict = skills.to_db_dict()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        self.conn.execute(
            """
            INSERT OR REPLACE INTO player_skills (
                player_id, clutch, speed, power, eye, contact, 
                base_running, bunting, catching, infield, outfield, 
                arm, accuracy, stamina, recovery, ground_balls, strikes,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                player_id,
                skill_dict["clutch"],
                skill_dict["speed"],
                skill_dict["power"],
                skill_dict["eye"],
                skill_dict["contact"],
                skill_dict["base_running"],
                skill_dict["bunting"],
                skill_dict["catching"],
                skill_dict["infield"],
                skill_dict["outfield"],
                skill_dict["arm"],
                skill_dict["accuracy"],
                skill_dict["stamina"],
                skill_dict["recovery"],
                skill_dict["ground_balls"],
                skill_dict["strikes"],
                now,
            ),
        )

        self.conn.commit()

    def snapshot_skills(self, player_id: str, season_id: str) -> None:
        """
        Save current skills to history for a season.
        Call this at the end of each season to track player progression.

        Args:
            player_id: Player ID
            season_id: Season ID to associate with this snapshot
        """
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()

        self.conn.execute(
            """
            INSERT OR REPLACE INTO player_skills_history (
                player_id, season_id,
                clutch, speed, power, eye, contact,
                base_running, bunting, catching, infield, outfield,
                arm, accuracy, stamina, recovery, ground_balls, strikes,
                recorded_at
            )
            SELECT 
                player_id, ?, 
                clutch, speed, power, eye, contact,
                base_running, bunting, catching, infield, outfield,
                arm, accuracy, stamina, recovery, ground_balls, strikes,
                ?
            FROM player_skills
            WHERE player_id = ?
            """,
            (season_id, now, player_id),
        )

        self.conn.commit()

    # ------------------------------------------------------------
    # READ
    # ------------------------------------------------------------

    def look_up(self, player_id: str) -> PlayerRecord | None:
        """
        Fetch a player with their current skills.

        Args:
            player_id: Player ID

        Returns:
            PlayerRecord if found, None otherwise

        Raises:
            ValueError: If player exists but has no skills record
        """
        # Get identity
        identity_row = self.conn.execute(
            """
            SELECT *
            FROM players
            WHERE id = ?
            """,
            (player_id,),
        ).fetchone()

        if identity_row is None:
            return None

        # Get current skills
        skills_row = self.conn.execute(
            """
            SELECT *
            FROM player_skills
            WHERE player_id = ?
            """,
            (player_id,),
        ).fetchone()

        if skills_row is None:
            # Player exists but has no skills yet (shouldn't happen in normal flow)
            raise ValueError(f"Player {player_id} has no skills record")

        skills = PlayerSkills.from_db_row(skills_row)

        return PlayerRecord(
            id=identity_row["id"],
            first_name=identity_row["first_name"],
            last_name=identity_row["last_name"],
            age=identity_row["age"],
            bats=identity_row["bats"],
            throws=identity_row["throws"],
            position=identity_row["position"],
            skills=skills,
        )

    def get_skill_history(self, player_id: str) -> list[dict]:
        """
        Get a player's skill progression across seasons.

        Args:
            player_id: Player ID

        Returns:
            List of dicts, each containing season_id and all skills for that season,
            ordered chronologically by season
        """
        rows = self.conn.execute(
            """
            SELECT *
            FROM player_skills_history
            WHERE player_id = ?
            ORDER BY season_id
            """,
            (player_id,),
        ).fetchall()

        return [dict(row) for row in rows]

    def exists(self, player_id: str) -> bool:
        """
        Check if a player exists.

        Args:
            player_id: Player ID

        Returns:
            True if player exists, False otherwise
        """
        row = self.conn.execute(
            "SELECT 1 FROM players WHERE id = ?", (player_id,)
        ).fetchone()

        return row is not None

    def get_all_players(self) -> list[PlayerRecord]:
        """
        Get all players in the database.

        Returns:
            List of PlayerRecord objects
        """
        rows = self.conn.execute("""
            SELECT p.*, ps.*
            FROM players p
            JOIN player_skills ps ON p.id = ps.player_id
            ORDER BY p.last_name, p.first_name
            """).fetchall()

        return [
            PlayerRecord(
                id=row["id"],
                first_name=row["first_name"],
                last_name=row["last_name"],
                age=row["age"],
                bats=row["bats"],
                throws=row["throws"],
                position=row["position"],
                skills=PlayerSkills.from_db_row(row),
            )
            for row in rows
        ]

    def _get_timestamp(self) -> str:
        """Helper: Get current UTC timestamp in ISO format."""
        return datetime.datetime.now(datetime.timezone.utc).isoformat()
