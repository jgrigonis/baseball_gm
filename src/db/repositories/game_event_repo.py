# src/db/repositories/game_event_repo.py


class GameEventRepository:
    def __init__(self, conn):
        self.conn = conn

    def insert_game_event(
        self,
        game_id: str,
        team_id: str,
        event_type: str,
        inning: int | None = None,
        half: str | None = None,
        player_id: str | None = None,
        player_id_2: str | None = None,
        reason: str | None = None,
        detail: str | None = None,
    ):
        self.conn.execute(
            """
            INSERT INTO game_events
                (game_id, inning, half, team_id, event_type,
                    player_id, player_id_2, reason, detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                game_id,
                inning,
                half,
                team_id,
                event_type,
                player_id,
                player_id_2,
                reason,
                detail,
            ),
        )
