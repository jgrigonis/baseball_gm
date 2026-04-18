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
            (gm_id, league_id, user_id, display_name, is_ai),
        )
        # Tucking this in here ensures every GM always has a profile
        self.conn.execute("INSERT INTO gm_profiles (gm_id) VALUES (%s)", (gm_id,))

    def get_human_team_ids(self, league_id: str) -> set[str]:
        """Return the set of team_ids belonging to human GMs in a league."""
        rows = self.conn.execute(
            "SELECT team_id FROM gms WHERE league_id = %s AND NOT is_ai AND team_id IS NOT NULL",
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
        self.conn.execute(
            """
                UPDATE gms SET user_id = %s
                WHERE NOT is_ai
                    AND user_id != %s
                    AND user_id IN (
                    SELECT id FROM users WHERE display_name = %s
                    )
            """,
            (user_id, user_id, user_display_name),
        )

    def get_users_leagues(self, user_id: str) -> list[dict]:
        """Fetch the user's leagues"""
        rows = self.conn.execute(
            """SELECT l.id, l.name, l.state, l.mode, l.created_at, l.join_code,
                      MAX(s.year) as current_year,
                      (l.commissioner_gm_id = g.id) as is_commissioner
            FROM leagues l
            JOIN gms g ON g.league_id = l.id
            LEFT JOIN league_seasons ls ON ls.league_id = l.id
            LEFT JOIN seasons s ON s.id = ls.season_id
            WHERE g.user_id = %s AND NOT g.is_ai
            GROUP BY l.id, l.name, l.state, l.mode, l.created_at, l.join_code, g.id
            ORDER BY l.created_at DESC""",
            (user_id,),
        ).fetchall()

        # Convert rows to plain dicts if your driver doesn't do it automatically
        return [dict(row) for row in rows]

    def get_profile(self, gm_id: str) -> dict | None:
        """Return the gm_profiles row for a GM, or None."""
        row = self.conn.execute(
            "SELECT * FROM gm_profiles WHERE gm_id = %s", (gm_id,)
        ).fetchone()
        return dict(row) if row else None

    def save_profile(self, gm_id: str, updates: dict) -> None:
        """Update strategy fields on gm_profiles."""
        set_clause = ", ".join(f"{col} = %s" for col in updates)
        self.conn.execute(
            f"UPDATE gm_profiles SET {set_clause}, updated_at = NOW() WHERE gm_id = %s",
            [*updates.values(), gm_id],
        )

    def get_all_in_league(self, league_id: str) -> list[dict]:
        """Fetch all the GMs in a league."""
        rows = self.conn.execute(
            "SELECT * FROM gms WHERE league_id = %s", (league_id,)
        ).fetchall()

        return [dict(row) for row in rows]
