# src/db/repositories/gm_repo.py
class GMRepository:
    def __init__(self, conn):
        self.conn = conn

    def create_gm(
        self,
        gm_id: str,
        league_id: str,
        user_id: str,
        display_name: str,
        is_ai: bool = False,
    ):
        """Creates a GM and their associated profile."""
        self.conn.execute(
            "INSERT INTO gms (id, league_id, user_id, display_name, is_ai) VALUES (%s, %s, %s, %s, %s)",
            (gm_id, league_id, user_id, display_name, 1 if is_ai else 0),
        )
        # Tucking this in here ensures every GM always has a profile
        self.conn.execute("INSERT INTO gm_profiles (gm_id) VALUES (%s)", (gm_id,))

    def get_by_user_and_league(self, user_id: str, league_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM gms WHERE user_id = %s AND league_id = %s",
            (user_id, league_id),
        ).fetchone()
        return dict(row) if row else None

    def set_commissioner(self, gm_id: str, league_id: str):
        """Set the commissioner."""
        self.conn.execute(
            "UPDATE leagues SET commissioner_gm_id = %s WHERE id = %s", (gm_id, league_id)
        )
