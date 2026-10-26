# src/db/repositories/team_rotations_repo.py
"""
This script can:

Set pitching rotation
Return current rotation
Get next starter
Update the pitching rotation


might want to pass the pitcher_repo into get_next_starter as an
argument instead of re-instantiating it in a loop.

"""

from typing import Any
from datetime import datetime, date

from src.db.repositories.pitcher_state import PitcherStateRepository, MIN_ENERGY_STARTER


class TeamRotationsRepository:
    """Repository for managing starting pitcher rotations."""

    def __init__(self, conn, league_id: str):
        self.conn = conn
        self.league_id = league_id

    def set_rotation(self, team_id, season_id, player_id_list, effective_date) -> None:
        """
        Set the pitching rotation.
        Creates initial rotation entries for a team/season

        Raises:
            ValueError: If an active rotation already exists for this team/season
        """
        # Check if active rotation already exists
        existing = self.conn.execute(
            """
            SELECT COUNT(*) FROM team_rotations
            WHERE team_id = %s AND season_id = %s AND end_date IS NULL
            """,
            (team_id, season_id),
        ).fetchone()["count"]

        if existing > 0:
            return  # already set, skip silently
            # raise ValueError(
            #     f"Active rotation already exists for team {team_id} in season {season_id}. "
            #     f"Use update_rotation() to modify it."
            # )

        for order, player_id in enumerate(player_id_list, 1):
            self.conn.execute(
                """
                INSERT INTO team_rotations (
                    team_id, season_id, player_id, rotation_order, effective_date, end_date
                )
                VALUES (%s, %s, %s, %s, %s, NULL)
                """,
                (team_id, season_id, player_id, order, effective_date),
            )

    def replace_rotation(
        self,
        team_id: str,
        season_id: str,
        player_ids: list[str],
        effective_date: str,
        next_order: int,
    ) -> None:
        """
        Closes existing rotation entries and opens new ones.
        Maintains history by setting end_date instead of deleting.
        """
        # 1. First, delete any entries that were already created for TODAY
        # This prevents the UniqueViolation if they save twice in one day.
        self.conn.execute(
            """
            DELETE FROM team_rotations 
            WHERE team_id = %s AND season_id = %s AND effective_date = %s
            """,
            (team_id, season_id, effective_date),
        )
        # 2. Close current active rotation slots
        self.conn.execute(
            """
            UPDATE team_rotations 
            SET end_date = %s 
            WHERE team_id = %s AND season_id = %s AND end_date IS NULL
            """,
            (effective_date, team_id, season_id),
        )

        # 3. Open the new rotation slots
        for order, pid in enumerate(player_ids, start=1):
            self.conn.execute(
                """
                INSERT INTO team_rotations 
                    (team_id, season_id, player_id, rotation_order, effective_date, end_date)
                VALUES (%s, %s, %s, %s, %s, NULL)
                """,
                (team_id, season_id, pid, order, effective_date),
            )

        # 4. Handle the bullpen role conflict (historically safe)
        if player_ids:
            placeholders = ", ".join(["%s"] * len(player_ids))
            self.conn.execute(
                f"""
                UPDATE bullpen_roles 
                SET end_date = %s
                WHERE team_id = %s AND season_id = %s 
                AND end_date IS NULL 
                AND player_id IN ({placeholders})
                """,
                (effective_date, team_id, season_id, *player_ids),
            )
        # 5. Update the pointer
        self.assign_rotation_pointer(
            team_id=team_id,
            season_id=season_id,
            next_order=next_order,
        )

    def get_current_rotation(
        self, team_id, season_id, as_of_date
    ) -> list[dict[str, Any]]:
        """
        Get the current active rotation for a team/season.

        Args:
            team_id: Team identifier
            season_id: Season identifier
            as_of_date: Date to check rotation as of (simulation date, required)

        Returns:
            List of dicts with rotation info, ordered by rotation_order:
            [
                {'player_id': 'P001', 'rotation_order': 1, 'effective_date': '2024-04-01'},
                {'player_id': 'P002', 'rotation_order': 2, 'effective_date': '2024-04-01'},
                ...
            ]
            Returns empty list if no active rotation found.
        """
        cursor = self.conn.execute(
            """
            SELECT player_id, rotation_order, effective_date, end_date
            FROM team_rotations
            WHERE team_id       = %s
            AND season_id       = %s
            AND effective_date::date <= %s
            AND (end_date IS NULL OR end_date::date > %s)
            ORDER BY rotation_order
            """,
            (team_id, season_id, as_of_date, as_of_date),
        )

        rows = cursor.fetchall()
        return [
            {
                "player_id": row["player_id"],
                "rotation_order": row["rotation_order"],
                "effective_date": row["effective_date"],
                "end_date": row["end_date"],
            }
            for row in rows
        ]

    def get_next_starter(
        self, team_id: str, season_id: str, current_date: str
    ) -> str | None:
        """
        Get the next pitcher in the rotation who should start.

        Args:
            team_id: Team identifier
            season_id: Season identifier
            current_date: Current simulation date

        Returns:
            player_id of the next starter, or None if no rotation exists

        Logic:
            - Gets the current active rotation
            - Finds the most recent game where a rotation pitcher started
            - Returns the next pitcher in rotation order (wraps from 5 -> 1)
            - If no previous starts found, returns rotation_order 1
        """
        # Get current rotation
        rotation = self.get_current_rotation(team_id, season_id, current_date)

        if not rotation:
            return None

        pitcher_repo = PitcherStateRepository(self.conn, league_id=self.league_id)
        # Find most recent starter from this team's rotation
        rotation_player_ids = [r["player_id"] for r in rotation]

        if not rotation_player_ids:
            return None

        cursor = self.conn.execute(
            """
            SELECT pgs.player_id, tr.rotation_order
            FROM player_game_stats pgs
            JOIN games g ON pgs.game_id = g.id
            JOIN team_rotations tr ON pgs.player_id = tr.player_id 
                AND g.season_id = tr.season_id
                AND pgs.team_id = tr.team_id
            WHERE pgs.team_id = %s
            AND g.season_id   = %s
            AND pgs.pitch_game_started = 1
            AND pgs.player_id IN ({})
            AND g.game_date::date <= %s
            AND tr.effective_date::date <= g.game_date::date
            AND (tr.end_date IS NULL OR tr.end_date::date > g.game_date::date)
            ORDER BY g.game_date DESC, g.id DESC
            LIMIT 1
            """.format(", ".join(["%s"] * len(rotation_player_ids))),
            (team_id, season_id, *rotation_player_ids, current_date),
        )

        last_starter = cursor.fetchone()
        last_rotation_order = last_starter["rotation_order"] if last_starter else 0

        # Try each pitcher in rotation order starting from next, skip if too tired
        game_date = (
            current_date
            if isinstance(current_date, date)
            else datetime.fromisoformat(current_date).date()
        )
        for i in range(len(rotation)):
            next_order = (last_rotation_order + i) % len(rotation) + 1
            candidate = next(
                (r for r in rotation if r["rotation_order"] == next_order), None
            )
            if not candidate:
                continue
            state = pitcher_repo.get_with_recovery(
                player_id=candidate["player_id"],
                game_date=game_date,
                recovery_skill=50,  # default; ideally pass actual skill
            )
            if state.current_energy >= MIN_ENERGY_STARTER:
                return candidate["player_id"]

        # All pitchers tired — return the most-rested one as fallback
        best = max(
            rotation,
            key=lambda r: (
                pitcher_repo.get_with_recovery(
                    r["player_id"], game_date, 50
                ).current_energy
            ),
        )
        return best["player_id"]

    def update_rotation(
        self,
        team_id: str,
        season_id: str,
        player_id: str,
        new_rotation_order: int,
        effective_date: str,
    ) -> None:
        """
        Update a single pitcher's rotation order.

        Ends the current assignment (sets end_date) if it exists and
        creates a new entry with the new rotation_order.

        Args:
            team_id: Team identifier
            season_id: Season identifier
            player_id: Player to update
            new_rotation_order: New position in rotation (1-5)
            effective_date: When this change takes effect
        """
        # Verify player is in current rotation
        cursor = self.conn.execute(
            """
            SELECT rotation_order, effective_date
            FROM team_rotations
            WHERE team_id       = %s
            AND season_id       = %s
            AND player_id       = %s
            AND effective_date::date <= %s
            AND (end_date IS NULL OR end_date::date > %s)
            ORDER BY effective_date DESC
            LIMIT 1
            """,
            (team_id, season_id, player_id, effective_date, effective_date),
        )
        current = cursor.fetchone()
        if current:
            current_order = current["rotation_order"]
            current_effective_date = current["effective_date"]

            # Don't update if order hasn't changed
            if current_order == new_rotation_order:
                return

            # End the current assignment
            self.conn.execute(
                """
                UPDATE team_rotations
                SET end_date       = %s
                WHERE team_id      = %s
                AND season_id      = %s
                AND player_id      = %s
                AND effective_date = %s
                AND end_date IS NULL
                """,
                (effective_date, team_id, season_id, player_id, current_effective_date),
            )

        # Create new entry with new rotation order
        self.conn.execute(
            """
            INSERT INTO team_rotations (
                team_id, season_id, player_id, rotation_order, effective_date, end_date
            )
            VALUES (%s, %s, %s, %s, %s, NULL)
            """,
            (team_id, season_id, player_id, new_rotation_order, effective_date),
        )

    # only ever called in tests
    def remove_from_rotation(
        self, team_id: str, season_id: str, player_id: str, effective_date: str
    ) -> None:
        """
        Remove a pitcher from the rotation.

        Sets end_date on the player's active rotation entry.
        Used for injuries, demotions, trades, etc.

        Args:
            team_id: Team identifier
            season_id: Season identifier
            player_id: Player to remove
            effective_date: When the removal takes effect

        Raises:
            ValueError: If player is not in active rotation
        """
        # Verify player is in current rotation
        cursor = self.conn.execute(
            """
            SELECT effective_date
            FROM team_rotations
            WHERE team_id       = %s
            AND season_id       = %s
            AND player_id       = %s
            AND effective_date::date <= %s
            AND (end_date IS NULL OR end_date::date > %s)
            ORDER BY effective_date DESC
            LIMIT 1
            """,
            (team_id, season_id, player_id, effective_date, effective_date),
        )

        current = cursor.fetchone()
        if not current:
            raise ValueError(
                f"Player {player_id} is not in active rotation for team {team_id} "
                f"in season {season_id} as of {effective_date}"
            )

        current_effective_date = current["effective_date"]

        # End the current assignment
        self.conn.execute(
            """
            UPDATE team_rotations
            SET end_date       = %s
            WHERE team_id      = %s
            AND season_id      = %s
            AND player_id      = %s
            AND effective_date = %s
            AND end_date IS NULL
            """,
            (effective_date, team_id, season_id, player_id, current_effective_date),
        )

    # Only ever called in tests
    def add_to_rotation(
        self,
        team_id: str,
        season_id: str,
        player_id: str,
        rotation_order: int,
        effective_date: str,
    ) -> None:
        """
        Add a new pitcher to the rotation.

        If the rotation_order is already occupied, shifts that pitcher and all
        subsequent pitchers down by one (e.g., adding at spot 3 moves 3->4, 4->5, 5->6).

        Args:
            team_id: Team identifier
            season_id: Season identifier
            player_id: Player to add
            rotation_order: Position in rotation (1-N)
            effective_date: When this takes effect

        Raises:
            ValueError: If player is already in active rotation
        """
        # Check if player is already in rotation
        existing = self.conn.execute(
            """
            SELECT COUNT(*) FROM team_rotations
            WHERE team_id       = %s
            AND season_id       = %s
            AND player_id       = %s
            AND effective_date::date <= %s
            AND (end_date IS NULL OR end_date::date > %s)
            """,
            (team_id, season_id, player_id, effective_date, effective_date),
        ).fetchone()["count"]

        if existing > 0:
            raise ValueError(
                f"Player {player_id} is already in active rotation for team {team_id} "
                f"in season {season_id}"
            )

        # Get current rotation
        current_rotation = self.get_current_rotation(team_id, season_id, effective_date)

        # Find pitchers that need to be shifted (rotation_order >= new pitcher's order)
        pitchers_to_shift = [
            p for p in current_rotation if p["rotation_order"] >= rotation_order
        ]

        # Shift existing pitchers down
        for pitcher in pitchers_to_shift:
            self.update_rotation(
                team_id,
                season_id,
                pitcher["player_id"],
                pitcher["rotation_order"] + 1,
                effective_date,
            )

        # Insert new pitcher
        self.conn.execute(
            """
            INSERT INTO team_rotations (
                team_id, season_id, player_id, rotation_order, effective_date, end_date
            )
            VALUES (%s, %s, %s, %s, %s, NULL)
            """,
            (team_id, season_id, player_id, rotation_order, effective_date),
        )

    # Only called in tests
    def swap_rotation_spots(
        self,
        team_id: str,
        season_id: str,
        player1_id: str,
        player2_id: str,
        effective_date: str,
    ) -> None:
        """
        Swap two pitchers' positions in the rotation.

        Convenience method that exchanges the rotation_order of two pitchers.

        Args:
            team_id: Team identifier
            season_id: Season identifier
            player1_id: First player to swap
            player2_id: Second player to swap
            effective_date: When the swap takes effect

        Raises:
            ValueError: If either player is not in active rotation
        """
        # Get both players' current rotation orders
        current_rotation = self.get_current_rotation(team_id, season_id, effective_date)

        player1_entry = next(
            (p for p in current_rotation if p["player_id"] == player1_id), None
        )
        player2_entry = next(
            (p for p in current_rotation if p["player_id"] == player2_id), None
        )

        if not player1_entry:
            raise ValueError(
                f"Player {player1_id} is not in active rotation for team {team_id} "
                f"in season {season_id}"
            )

        if not player2_entry:
            raise ValueError(
                f"Player {player2_id} is not in active rotation for team {team_id} "
                f"in season {season_id}"
            )

        player1_order = player1_entry["rotation_order"]
        player2_order = player2_entry["rotation_order"]

        # Swap via a temporary order to avoid any ambiguity mid-swap
        # TEMP_ORDER = 9999
        # TEMP_DATE = "9999-01-01"
        # self.update_rotation(team_id, season_id, player1_id, TEMP_ORDER, TEMP_DATE)
        self.update_rotation(
            team_id, season_id, player2_id, player1_order, effective_date
        )
        self.update_rotation(
            team_id, season_id, player1_id, player2_order, effective_date
        )

    def get_scheduled_starter(
        self,
        team_id: str,
        season_id: str,
        series_id: str = "",
    ) -> str | None:
        """
        Return the player_id of the scheduled next starter for this team,
        based on the rotation pointer. Creates the pointer at order 1 if
        it doesn't exist yet. Returns None if the team has no active rotation.
        """
        # Ensure pointer row exists
        self.conn.execute(
            """
            INSERT INTO team_rotation_pointer
                (team_id, season_id, series_id, next_order)
            VALUES (%s, %s, %s, 1)
            ON CONFLICT DO NOTHING
            """,
            (team_id, season_id, series_id),
        )

        row = self.conn.execute(
            """
            SELECT next_order
            FROM team_rotation_pointer
            WHERE team_id = %s AND season_id = %s AND series_id = %s
            """,
            (team_id, season_id, series_id),
        ).fetchone()

        next_order = row["next_order"]

        starter = self.conn.execute(
            """
            SELECT player_id
            FROM team_rotations
            WHERE team_id      = %s
            AND season_id      = %s
            AND rotation_order = %s
            AND end_date IS NULL
            LIMIT 1
            """,
            (team_id, season_id, next_order),
        ).fetchone()

        if starter:
            return starter["player_id"]

        # Pointer is pointing at a gap (e.g. sp1 slot was closed mid-season).
        # Fall back to the lowest available active slot so the team still fields
        # a starter rather than triggering the "No rotation" warning.
        fallback = self.conn.execute(
            """
            SELECT player_id
            FROM team_rotations
            WHERE team_id  = %s
            AND season_id  = %s
            AND end_date IS NULL
            ORDER BY rotation_order
            LIMIT 1
            """,
            (team_id, season_id),
        ).fetchone()

        return fallback["player_id"] if fallback else None

    def advance_rotation_pointer(
        self,
        team_id: str,
        season_id: str,
        series_id: str = "",
        after_player_id: str | None = None,
    ) -> None:
        """
        Advance the rotation pointer to the next actual rotation_order slot,
        wrapping around. Safe against gaps caused by remove_from_rotation.
        No-op if the team has no active rotation entries.

        With ``after_player_id`` (the pitcher who just started), the pointer
        moves to the slot after that pitcher's, so a rested pitcher filling
        in for a tired one isn't scheduled again next game.  If that pitcher
        isn't in the rotation, it advances from the current pointer instead.
        """
        # Get actual sorted rotation_orders (may have gaps after removals)
        order_rows = self.conn.execute(
            """
            SELECT rotation_order, player_id FROM team_rotations
            WHERE team_id = %s AND season_id = %s AND end_date IS NULL
            ORDER BY rotation_order
            """,
            (team_id, season_id),
        ).fetchall()

        orders = [r["rotation_order"] for r in order_rows]
        if not orders:
            return

        started_order = next(
            (
                r["rotation_order"]
                for r in order_rows
                if after_player_id and r["player_id"] == after_player_id
            ),
            None,
        )

        if started_order is not None:
            current = started_order
        else:
            pointer_row = self.conn.execute(
                """
                SELECT next_order
                FROM team_rotation_pointer
                WHERE team_id = %s AND season_id = %s AND series_id = %s
                """,
                (team_id, season_id, series_id),
            ).fetchone()
            current = pointer_row["next_order"] if pointer_row else orders[0]

        # Find the next order after current in the actual list, wrapping around
        orders_after = [o for o in orders if o > current]
        new_order = orders_after[0] if orders_after else orders[0]

        self.conn.execute(
            """
            INSERT INTO team_rotation_pointer
                (team_id, season_id, series_id, next_order, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (team_id, season_id, series_id)
            DO UPDATE SET next_order = excluded.next_order,
                        updated_at = excluded.updated_at
            """,
            (team_id, season_id, series_id, new_order),
        )

    # def set_pointer_to_one(self, team_id: str, season_id: str, series_id: str = '') -> None:
    #     """Set the rotation pointer to sp1."""
    #     self.conn.execute(
    #         """INSERT INTO team_rotation_pointer
    #         (team_id, season_id, series_id, next_order, updated_at)
    #         VALUES(%s, %s, %s, 1, NOW())
    #         ON CONFLICT (team_id, season_id, series_id)
    #                DO UPDATE SET next_order = 1,
    #                              updated_at = excluded.updated_at
    #         """,
    #         (team_id, season_id, series_id)
    #     )

    def reset_rotation_pointers(self, season_id: str) -> int:
        """
        Reset all rotation pointers for a season back to order 1.
        Call at the start of each new season so game 1 always starts sp1.
        Returns the number of rows upserted.
        """
        team_rows = self.conn.execute(
            """SELECT DISTINCT team_id FROM team_rotations
               WHERE season_id = %s AND end_date IS NULL""",
            (season_id,),
        ).fetchall()

        count = 0
        for row in team_rows:
            # self.set_pointer_to_one(row["team_id"], season_id)
            self.assign_rotation_pointer(row["team_id"], season_id, 1)
            # self.conn.execute(
            #     """INSERT INTO team_rotation_pointer
            #            (team_id, season_id, series_id, next_order, updated_at)
            #        VALUES (%s, %s, '', 1, NOW())
            #        ON CONFLICT (team_id, season_id, series_id)
            #        DO UPDATE SET next_order = 1,
            #                      updated_at = excluded.updated_at""",
            #     (row["team_id"], season_id),
            # )
            count += 1

        return count

    def get_saved_rotation(self, team_id: str, season_id: str) -> list[str]:
        """Return player_ids in current active rotation order (no date filtering)."""
        rows = self.conn.execute(
            """SELECT player_id FROM team_rotations
               WHERE team_id = %s AND season_id = %s AND end_date IS NULL
               ORDER BY rotation_order""",
            (team_id, season_id),
        ).fetchall()
        return [r["player_id"] for r in rows]

    def get_rotation_pointer_player(self, team_id: str, season_id: str) -> str | None:
        """Return the player_id at the current rotation pointer (read-only). None if unset."""
        ptr = self.conn.execute(
            """SELECT next_order FROM team_rotation_pointer
               WHERE team_id = %s AND season_id = %s AND series_id = ''""",
            (team_id, season_id),
        ).fetchone()
        if not ptr:
            return None
        row = self.conn.execute(
            """SELECT player_id FROM team_rotations
               WHERE team_id = %s AND season_id = %s AND rotation_order = %s
               AND end_date IS NULL""",
            (team_id, season_id, ptr["next_order"]),
        ).fetchone()
        return row["player_id"] if row else None

    def assign_rotation_pointer(
        self, team_id: str, season_id: str, next_order: int, series_id: str = ""
    ) -> None:
        """
        Assign the pointer to a specific rotation order slot (e.g., 1 through 5).
        """
        self.conn.execute(
            """INSERT INTO team_rotation_pointer
                    (team_id, season_id, series_id, next_order, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (team_id, season_id, series_id)
                DO UPDATE SET 
                    next_order = EXCLUDED.next_order,
                    updated_at = EXCLUDED.updated_at""",
            (team_id, season_id, series_id, next_order),
        )


# get_rotation_history(team_id, season_id, player_id=None)

# View all rotation changes for analysis
# Optional filter by specific player
