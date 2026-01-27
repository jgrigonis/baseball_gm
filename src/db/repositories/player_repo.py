# src/db/repositories/player_repo.py
import sqlite3
from datetime import datetime
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills


class PlayerRepository:
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
    ):
        """
        Create a player record with identity and initial skills.
        Idempotent per (id).
        """
        # Insert identity
        self.conn.execute(
            """
            INSERT OR REPLACE INTO players (
                id, first_name, last_name, bats, throws, position
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (id, first_name, last_name, bats, throws, position),
        )

        # Insert or update skills
        self.update_skills(id, skills)

        self.conn.commit()

    def update_skills(self, player_id: str, skills: PlayerSkills):
        """
        Update a player's current skills.
        Used for training, aging, etc.
        """
        skill_dict = skills.to_db_dict()
        now = datetime.utcnow().isoformat()

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

    def snapshot_skills(self, player_id: str, season_id: str):
        """
        Save current skills to history for a season.
        Call this at the end of each season to track progression.
        """
        now = datetime.utcnow().isoformat()

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
        Fetch a player with current skills
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
            bats=identity_row["bats"],
            throws=identity_row["throws"],
            position=identity_row["position"],
            skills=skills,
        )

    def get_skill_history(self, player_id: str) -> list[dict]:
        """
        Get a player's skill progression across seasons.
        Returns list of dicts with season_id and all skills.
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
