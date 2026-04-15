# src/db/repositories/lineup_preference_repo.py


class LineupPreferenceRepository:
    def __init__(self, conn):
        self.conn = conn

    def save_preferences(self, gm_id: str, lineup: list[dict]):
        self.conn.execute(
            "DELETE FROM gm_lineup_preferences WHERE gm_id = %s", (gm_id,)
        )
        for slot in lineup:
            self.conn.execute(
                """INSERT INTO gm_lineup_preferences
                   (gm_id, player_id, batting_order, position, is_starter, updated_at)
                   VALUES (%s, %s, %s, %s, 1, NOW())""",
                (gm_id, slot["player_id"], slot["batting_order"], slot.get("position")),
            )

    def get_by_gm_id(self, gm_id: str) -> list[dict]:
        """Return saved batting order for a GM (batting_order slots only), ordered."""
        rows = self.conn.execute(
            """SELECT player_id, batting_order, position FROM gm_lineup_preferences
               WHERE gm_id = %s AND batting_order IS NOT NULL
               ORDER BY batting_order""",
            (gm_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_preferences(self, team_id: str, league_id: str) -> list[dict] | None:
        # This moved from _load_saved_lineup in play_season
        gm = self.conn.execute(
            "SELECT id FROM gms WHERE team_id = %s AND league_id = %s AND is_ai = 0 LIMIT 1",
            (team_id, league_id),
        ).fetchone()
        if not gm:
            return None
        rows = self.conn.execute(
            "SELECT player_id, batting_order, position FROM gm_lineup_preferences WHERE gm_id = %s ORDER BY batting_order",
            (gm["id"],),
        ).fetchall()
        return [dict(r) for r in rows] if rows else None
