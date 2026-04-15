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

    def get_human_team_ids(self, league_id: str) -> set[str]:
        """Return the set of team_ids belonging to human GMs in a league."""
        rows = self.conn.execute(
            "SELECT team_id FROM gms WHERE league_id = %s AND is_ai = 0 AND team_id IS NOT NULL",
            (league_id,),
        ).fetchall()
        return {r["team_id"] for r in rows}

    def get_by_user_and_league(self, user_id: str, league_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM gms WHERE user_id = %s AND league_id = %s",
            (user_id, league_id),
        ).fetchone()
        return dict(row) if row else None

    def set_commissioner(self, gm_id: str, league_id: str):
        """Set the commissioner."""
        self.conn.execute(
            "UPDATE leagues SET commissioner_gm_id = %s WHERE id = %s",
            (gm_id, league_id),
        )
    
    def auto_link_gm_account(self, user_id: str, user_display_name: str):
        """ 
        Identity Reclaim (Auto-linking)
        We still need this for now since we aren't doing 2FA/Logins yet,
        but the dependency ensures 'user' is already valid.
        Auto-reclaim: any gm row with same display_name but different user_id
        gets reassigned to the current user. This handles the common case where
        the browser cookie was cleared and a new guest identity was created.
        """
        self.db.execute(
            """
                UPDATE gms SET user_id = %s
                WHERE is_ai = 0
                    AND user_id != %s
                    AND user_id IN (
                    SELECT id FROM users WHERE display_name = %s
                    )
            """,
            (user_id, user_id, user_display_name),
        )

    def get_users_leagues(self, user_id: str) -> list[dict]:
        """Fetch the user's leagues"""
        rows = self.db.execute(
            """SELECT l.id, l.name, l.state, l.mode, l.created_at 
            FROM leagues l
            JOIN gms g ON g.league_id = l.id
            WHERE g.user_id = %s AND g.is_ai = 0
            ORDER BY l.created_at DESC""",
            (user_id,),
        ).fetchall()
        
        # Convert rows to plain dicts if your driver doesn't do it automatically
        return [dict(row) for row in rows]
