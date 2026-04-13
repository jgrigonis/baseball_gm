# src/db/repositories/game_lineup_repo.py

from src.player.player_in_game import PlayerInGame
from src.team.lineup_slot import LineupSlot


class LineupRepository:
    def __init__(self, conn):
        self.conn = conn

    def save_lineup(
        self,
        game_id: str,
        team_id: str,
        lineup: list[LineupSlot],
        pitcher: PlayerInGame,
    ) -> None:
        cursor = self.conn.cursor()
        cursor.execute(
            "DELETE FROM game_lineup_slots WHERE game_id = %s AND team_id = %s",
            (game_id, team_id),
        )

        for order, slot in enumerate(lineup, start=1):
            cursor.execute(
                """
                INSERT INTO game_lineup_slots
                    (game_id, team_id, player_id, position, batting_order, is_pitcher)
                VALUES (%s, %s, %s, %s, %s, 0)
                """,
                (game_id, team_id, slot.player.id, slot.position, order),
            )

        if pitcher:
            cursor.execute(
                """
                INSERT INTO game_lineup_slots
                    (game_id, team_id, player_id, position, batting_order, is_pitcher)
                VALUES (%s, %s, %s, 'p', NULL, 1)
                """,
                (game_id, team_id, pitcher.id),
            )

        # self.conn.commit()

    def get_lineup(self, game_id: str, team_id: str) -> list[dict]:
        cursor = self.conn.cursor()
        cursor.execute(
            """
            SELECT ls.player_id, p.first_name || ' ' || p.last_name AS name,
                   ls.position, ls.batting_order, ls.is_pitcher
            FROM game_lineup_slots ls
            JOIN players p ON ls.player_id = p.id
            WHERE ls.game_id = %s AND ls.team_id = %s
            ORDER BY ls.is_pitcher, ls.batting_order
            """,
            (game_id, team_id),
        )
        return [dict(r) for r in cursor.fetchall()]
