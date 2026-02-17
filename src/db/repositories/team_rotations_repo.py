# src/db/repositories/team_rotations_repo.py
"""
This script can:

Set pitching rotation
Return current rotation
Get next starter
Update the pitching rotation

"""
import datetime
from typing import Any
import uuid

class TeamRotationsRepository:
    """Repository for managing starting pitcher rotations."""

    def __init__(self, conn):
        self.conn = conn
    
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
            WHERE team_id = ? AND season_id = ? AND end_date IS NULL
            """,
            (team_id, season_id)
        ).fetchone()[0]

        if existing > 0:
            raise ValueError(
                f"Active rotation already exists for team {team_id} in season {season_id}. "
                f"Use update_rotation() to modify it."
            )
        
        for order, player_id in enumerate(player_id_list, 1):
            self.conn.execute(
                """
                INSERT INTO team_rotations (
                    team_id, season_id, player_id, rotation_order, effective_date, end_date
                )
                VALUES (?, ?, ?, ?, ?, NULL)
                """,
                (team_id, season_id, player_id, order, effective_date),
            )
        
        self.conn.commit()
    
    def get_current_rotation(self, team_id, season_id, as_of_date) -> list[dict[str, Any]]:
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
            WHERE team_id = ?
            AND season_id = ?
            AND effective_date <= ?
            AND (end_date IS NULL OR end_date > ?)
            ORDER BY rotation_order
            """,
            (team_id, season_id, as_of_date, as_of_date)
        )
        
        rows = cursor.fetchall()
        return [
            {
                'player_id': row[0],
                'rotation_order': row[1],
                'effective_date': row[2],
                'end_date': row[3]
            }
            for row in rows
        ]


    def get_next_starter(self, team_id: str, season_id: str, current_date: str) -> str | None:
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
        
        # Find most recent starter from this team's rotation
        rotation_player_ids = [r['player_id'] for r in rotation]
        
        cursor = self.conn.execute(
            """
            SELECT pgs.player_id, tr.rotation_order
            FROM player_game_stats pgs
            JOIN games g ON pgs.game_id = g.id
            JOIN team_rotations tr ON pgs.player_id = tr.player_id 
                AND g.season_id = tr.season_id
                AND pgs.team_id = tr.team_id
            WHERE pgs.team_id = ?
            AND g.season_id = ?
            AND pgs.pitch_game_started = 1
            AND pgs.player_id IN ({})
            AND g.date < ?
            AND tr.effective_date <= g.date
            AND (tr.end_date IS NULL OR tr.end_date > g.date)
            ORDER BY g.date DESC
            LIMIT 1
            """.format(','.join('?' * len(rotation_player_ids))),
            (team_id, season_id, *rotation_player_ids, current_date)
        )
        
        last_starter = cursor.fetchone()
        
        if last_starter:
            last_rotation_order = last_starter[1]
            # Get next in rotation (wrap around)
            next_order = (last_rotation_order % len(rotation)) + 1
        else:
            # No previous starts, use first pitcher
            next_order = 1
        
        # Find pitcher with next_order
        for entry in rotation:
            if entry['rotation_order'] == next_order:
                return entry['player_id']
        
        return None


    def update_rotation(self, team_id: str, season_id: str, player_id: str, 
                    new_rotation_order: int, effective_date: str) -> None:
        """
        Update a pitcher's rotation order.
        
        Ends the current assignment (sets end_date) and creates a new entry 
        with the new rotation_order.
        
        Args:
            team_id: Team identifier
            season_id: Season identifier
            player_id: Player to update
            new_rotation_order: New position in rotation (1-5)
            effective_date: When this change takes effect
            
        Raises:
            ValueError: If player is not in active rotation or if new_rotation_order is invalid
        """
        # Verify player is in current rotation
        cursor = self.conn.execute(
            """
            SELECT rotation_order, effective_date
            FROM team_rotations
            WHERE team_id = ?
            AND season_id = ?
            AND player_id = ?
            AND effective_date <= ?
            AND (end_date IS NULL OR end_date > ?)
            ORDER BY effective_date DESC
            LIMIT 1
            """,
            (team_id, season_id, player_id, effective_date, effective_date)
        )
        
        current = cursor.fetchone()
        if not current:
            raise ValueError(
                f"Player {player_id} is not in active rotation for team {team_id} "
                f"in season {season_id} as of {effective_date}"
            )
        
        current_order, current_effective_date = current
        
        # Don't update if order hasn't changed
        if current_order == new_rotation_order:
            return
        
        # End the current assignment
        self.conn.execute(
            """
            UPDATE team_rotations
            SET end_date = ?
            WHERE team_id = ?
            AND season_id = ?
            AND player_id = ?
            AND effective_date = ?
            AND end_date IS NULL
            """,
            (effective_date, team_id, season_id, player_id, current_effective_date)
        )
        
        # Create new entry with new rotation order
        self.conn.execute(
            """
            INSERT INTO team_rotations (
                team_id, season_id, player_id, rotation_order, effective_date, end_date
            )
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (team_id, season_id, player_id, new_rotation_order, effective_date)
        )
        
        self.conn.commit()



    def remove_from_rotation(self, team_id: str, season_id: str, player_id: str, 
                            effective_date: str) -> None:
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
            WHERE team_id = ?
            AND season_id = ?
            AND player_id = ?
            AND effective_date <= ?
            AND (end_date IS NULL OR end_date > ?)
            ORDER BY effective_date DESC
            LIMIT 1
            """,
            (team_id, season_id, player_id, effective_date, effective_date)
        )
        
        current = cursor.fetchone()
        if not current:
            raise ValueError(
                f"Player {player_id} is not in active rotation for team {team_id} "
                f"in season {season_id} as of {effective_date}"
            )
        
        current_effective_date = current[0]
        
        # End the current assignment
        self.conn.execute(
            """
            UPDATE team_rotations
            SET end_date = ?
            WHERE team_id = ?
            AND season_id = ?
            AND player_id = ?
            AND effective_date = ?
            AND end_date IS NULL
            """,
            (effective_date, team_id, season_id, player_id, current_effective_date)
        )
        
        self.conn.commit()


    def add_to_rotation(self, team_id: str, season_id: str, player_id: str, 
                    rotation_order: int, effective_date: str) -> None:
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
            WHERE team_id = ?
            AND season_id = ?
            AND player_id = ?
            AND effective_date <= ?
            AND (end_date IS NULL OR end_date > ?)
            """,
            (team_id, season_id, player_id, effective_date, effective_date)
        ).fetchone()[0]
        
        if existing > 0:
            raise ValueError(
                f"Player {player_id} is already in active rotation for team {team_id} "
                f"in season {season_id}"
            )
        
        # Get current rotation
        current_rotation = self.get_current_rotation(team_id, season_id, effective_date)
        
        # Find pitchers that need to be shifted (rotation_order >= new pitcher's order)
        pitchers_to_shift = [
            p for p in current_rotation if p['rotation_order'] >= rotation_order
        ]
        
        # Shift existing pitchers down
        for pitcher in pitchers_to_shift:
            self.update_rotation(
                team_id, season_id, pitcher['player_id'], 
                pitcher['rotation_order'] + 1, effective_date
            )
        
        # Insert new pitcher
        self.conn.execute(
            """
            INSERT INTO team_rotations (
                team_id, season_id, player_id, rotation_order, effective_date, end_date
            )
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (team_id, season_id, player_id, rotation_order, effective_date)
        )
        
        self.conn.commit()


    def swap_rotation_spots(self, team_id: str, season_id: str, player1_id: str, 
                        player2_id: str, effective_date: str) -> None:
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
        
        player1_entry = next((p for p in current_rotation if p['player_id'] == player1_id), None)
        player2_entry = next((p for p in current_rotation if p['player_id'] == player2_id), None)
        
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
        
        player1_order = player1_entry['rotation_order']
        player2_order = player2_entry['rotation_order']
        
        # Swap the rotation orders
        self.update_rotation(team_id, season_id, player1_id, player2_order, effective_date)
        self.update_rotation(team_id, season_id, player2_id, player1_order, effective_date)


# get_rotation_history(team_id, season_id, player_id=None)

# View all rotation changes for analysis
# Optional filter by specific player

