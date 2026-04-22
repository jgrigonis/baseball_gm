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
from src.db.repositories.player_status_repo import PlayerStatusRepository
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
        league_id=None,
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
            INSERT INTO players (
                id, first_name, last_name, bats, throws, position, league_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (id, first_name, last_name, bats, throws, position, league_id),
        )

        # Insert or update skills
        self.update_skills(id, skills)

        # self.conn.commit()

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
            INSERT INTO player_skills (
                player_id, age, clutch, speed, power, eye, contact,
                base_running, bunting, catching, infield, outfield,
                arm, accuracy, stamina, recovery, ground_balls, strikes,
                durability, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (player_id) DO UPDATE SET
                age = EXCLUDED.age, clutch = EXCLUDED.clutch, speed = EXCLUDED.speed,
                power = EXCLUDED.power, eye = EXCLUDED.eye, contact = EXCLUDED.contact,
                base_running = EXCLUDED.base_running, bunting = EXCLUDED.bunting,
                catching = EXCLUDED.catching, infield = EXCLUDED.infield,
                outfield = EXCLUDED.outfield, arm = EXCLUDED.arm,
                accuracy = EXCLUDED.accuracy, stamina = EXCLUDED.stamina,
                recovery = EXCLUDED.recovery, ground_balls = EXCLUDED.ground_balls,
                strikes = EXCLUDED.strikes, durability = EXCLUDED.durability,
                updated_at = EXCLUDED.updated_at
            """,
            (
                player_id,
                skill_dict["age"],
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
                skill_dict["durability"],
                now,
            ),
        )

        # self.conn.commit()

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
            INSERT INTO player_skills_history (
                player_id, season_id,
                age, clutch, speed, power, eye, contact,
                base_running, bunting, catching, infield, outfield,
                arm, accuracy, stamina, recovery, ground_balls, strikes,
                durability, recorded_at
            )
            SELECT 
                player_id, %s, 
                age, clutch, speed, power, eye, contact,
                base_running, bunting, catching, infield, outfield,
                arm, accuracy, stamina, recovery, ground_balls, strikes,
                durability, %s
            FROM player_skills
            WHERE player_id = %s
            ON CONFLICT (player_id, season_id) DO UPDATE SET
                age = EXCLUDED.age, clutch = EXCLUDED.clutch, speed = EXCLUDED.speed,
                power = EXCLUDED.power, eye = EXCLUDED.eye, contact = EXCLUDED.contact,
                base_running = EXCLUDED.base_running, bunting = EXCLUDED.bunting,
                catching = EXCLUDED.catching, infield = EXCLUDED.infield,
                outfield = EXCLUDED.outfield, arm = EXCLUDED.arm,
                accuracy = EXCLUDED.accuracy, stamina = EXCLUDED.stamina,
                recovery = EXCLUDED.recovery, ground_balls = EXCLUDED.ground_balls,
                strikes = EXCLUDED.strikes, durability = EXCLUDED.durability,
                recorded_at = EXCLUDED.recorded_at
            """,
            (season_id, now, player_id),
        )

        # self.conn.commit()

    def delete_unassigned_prospects(self, league_id: str) -> None:
        self.conn.execute(
            """
            DELETE FROM players WHERE id IN (
                SELECT p.id FROM players p
                JOIN player_status ps ON ps.player_id = p.id
                LEFT JOIN team_players tp ON tp.player_id = p.id
                WHERE ps.status = 'prospect'
                AND tp.player_id IS NULL
                AND p.league_id = %s
            )
        """,
            (league_id,),
        )

    def clear_stale_prospects(self, league_id: str) -> int:
        cleared = 0
        psr = PlayerStatusRepository(self.conn)
        with self.conn.cursor() as cur:
            rows = cur.execute(
                """
                SELECT p.id
                FROM players p
                JOIN player_status ps ON p.id = ps.player_id
                LEFT JOIN team_players tp ON p.id = tp.player_id
                WHERE ps.status = 'prospect'
                AND tp.player_id IS NULL
                AND p.league_id = %s
                """,
                (league_id,),
            ).fetchall()
            for row in rows:
                player = self.look_up(row["id"])
                if player and player.age >= 24:
                    psr.set_status(player.id, "free_agent")
                    cleared += 1
        return cleared

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
            WHERE id = %s
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
            WHERE player_id = %s
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

    def get_player_skills(self, player_id: str) -> dict:
        """Return the player's skill dict, or an empty dict if none found."""
        row = self.conn.execute(
            """
            SELECT durability, clutch, speed, power, 
            eye, contact, base_running, bunting, 
            catching, infield, outfield, arm,
            accuracy, stamina, recovery, ground_balls,
            strikes
            FROM player_skills WHERE player_id = %s
            """,
            (player_id,),
        ).fetchone()
        return dict(row) if row else {}

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
            WHERE player_id = %s
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
            "SELECT 1 FROM players WHERE id = %s", (player_id,)
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
                bats=row["bats"],
                throws=row["throws"],
                position=row["position"],
                skills=PlayerSkills.from_db_row(row),
            )
            for row in rows
        ]

    def get_players_by_league(self, league_id: str) -> list[PlayerRecord]:
        """Get all players belonging to a league, including prospects."""
        rows = self.conn.execute(
            """SELECT p.*, ps.*
               FROM players p
               JOIN player_skills ps ON p.id = ps.player_id
               WHERE p.league_id = %s
               ORDER BY p.last_name, p.first_name""",
            (league_id,),
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

    def get_players_in_league_season(
        self, league_id: str, season_id: str
    ) -> list[PlayerRecord]:
        """Get all players on teams in the given league/season."""
        rows = self.conn.execute(
            """SELECT DISTINCT p.*, ps.*
               FROM players p
               JOIN player_skills ps ON p.id = ps.player_id
               JOIN team_players tp ON tp.player_id = p.id
               JOIN league_season_teams lst ON lst.team_id = tp.team_id
               WHERE lst.league_id = %s AND lst.season_id = %s
               ORDER BY p.last_name, p.first_name""",
            (league_id, season_id),
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

    def get_players_by_team(self, team_id: str) -> list[PlayerRecord]:
        rows = self.conn.execute(
            """
            SELECT p.*, ps.*
            FROM players p
            JOIN player_skills ps ON p.id = ps.player_id
            JOIN team_players tp ON p.id = tp.player_id
            WHERE tp.team_id = %s
            ORDER BY p.last_name, p.first_name
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

    def get_with_skills(self, player_id: str) -> dict | None:
        """Return a player row merged with their skill row as a flat dict, or None."""
        row = self.conn.execute(
            """SELECT p.*, sk.*
               FROM players p
               LEFT JOIN player_skills sk ON sk.player_id = p.id
               WHERE p.id = %s""",
            (player_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_team_roster_with_skills(self, team_id: str) -> list[dict]:
        """Return all players on a team with status and skills merged into flat dicts."""
        rows = self.conn.execute(
            """SELECT p.*, ps_stat.status, sk.*
               FROM players p
               JOIN team_players tp ON tp.player_id = p.id AND tp.team_id = %s
               JOIN player_status ps_stat ON ps_stat.player_id = p.id
               LEFT JOIN player_skills sk ON sk.player_id = p.id
               ORDER BY ps_stat.status, p.last_name""",
            (team_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_active_roster_with_skills(self, team_id: str) -> list[dict]:
        """Return 26-man/40-man players with skills merged, ordered by last name."""
        rows = self.conn.execute(
            """SELECT p.*, ps.status, sk.*
               FROM players p
               JOIN team_players tp ON tp.player_id = p.id AND tp.team_id = %s
               JOIN player_status ps ON ps.player_id = p.id
               LEFT JOIN player_skills sk ON sk.player_id = p.id
               WHERE ps.status IN ('26man', '40man')
               ORDER BY p.last_name""",
            (team_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def _get_timestamp(self) -> str:
        """Helper: Get current UTC timestamp in ISO format."""
        return datetime.datetime.now(datetime.timezone.utc).isoformat()

    def get_player_ids_from_team_players(self, team_id: str) -> set[str]:
        player_ids = self.conn.execute(
            "SELECT player_id FROM team_players WHERE team_id = %s",
            (team_id,),
        ).fetchall()
        return {r["player_id"] for r in player_ids}
        # return player_ids

    def get_retired_players_season_stats(
        self, team_id: str, league_id: str, season_id: str
    ) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT
                pr.player_id,
                pr.former_team_id,
                p.first_name,
                p.last_name,
                p.position,
                ps.age,
                COALESCE(t.city || ' ' || t.mascot, '—') AS team_name,
                (pr.former_team_id = %s)                  AS is_mine,
                -- batting
                pss.bat_games_played,
                pss.bat_ab,
                pss.bat_hits,
                pss.bat_home_runs,
                pss.bat_rbi,
                pss.bat_walks,
                pss.bat_strike_outs,
                pss.bat_doubles,
                pss.bat_triples,
                pss.bat_stolen_bases,
                -- pitching
                pss.pitch_games_played,
                pss.pitch_games_started,
                pss.pitch_wins,
                pss.pitch_losses,
                pss.pitch_saves,
                pss.pitch_outs,
                pss.pitch_earned_runs,
                pss.pitch_hits,
                pss.pitch_walks,
                pss.pitch_strike_outs
            FROM player_retirements pr
            JOIN players           p   ON p.id  = pr.player_id
            JOIN player_skills     ps  ON ps.player_id = pr.player_id
            LEFT JOIN teams        t   ON t.id  = pr.former_team_id
            LEFT JOIN player_season_stats pss
                ON pss.player_id  = pr.player_id
               AND pss.season_id  = pr.season_id
               AND pss.is_postseason = FALSE
            WHERE pr.league_id = %s
              AND pr.season_id  = %s
            ORDER BY
                (pr.former_team_id IS NOT NULL) DESC,
                (pr.former_team_id = %s) DESC,
                p.last_name, p.first_name
            """,
            (team_id, league_id, season_id, team_id),
        ).fetchall()
        return rows

    def get_career_stats(self, player_id: str) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT pss.*, s.year, t.city as team_city, t.mascot as team_mascot
            FROM player_season_stats pss
            JOIN seasons s ON s.id = pss.season_id
            JOIN teams t ON t.id = pss.team_id
            WHERE pss.player_id = %s
            ORDER BY s.year DESC, pss.is_postseason DESC
            """,
            (player_id,),
        ).fetchall()
        return rows
