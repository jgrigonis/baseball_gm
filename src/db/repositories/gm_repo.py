# src/db/repositories/gm_repo.py
import uuid


class GMRepository:
    def __init__(self, conn):
        self.conn = conn

    def create_gm(
        self,
        league_id: str,
        display_name: str,
        user_id: str | None = None,
        team_id: str | None = None,
        is_ai: bool = False,
    ) -> str:
        """Creates a GM and their associated profile."""
        gm_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO gms (id, league_id, user_id, team_id, display_name, is_ai) VALUES (%s, %s, %s, %s, %s, %s)",
            (gm_id, league_id, user_id, team_id, display_name, is_ai),
        )
        # Tucking this in here ensures every GM always has a profile
        self.conn.execute("INSERT INTO gm_profiles (gm_id) VALUES (%s)", (gm_id,))
        return gm_id

    def get_human_team_ids(self, league_id: str) -> set[str]:
        """Return the set of team_ids belonging to human GMs in a league."""
        rows = self.conn.execute(
            "SELECT team_id FROM gms WHERE league_id = %s AND NOT is_ai AND team_id IS NOT NULL",
            (league_id,),
        ).fetchall()
        return {r["team_id"] for r in rows}

    def get_human_gm_ids(self, league_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT id FROM gms WHERE league_id = %s AND NOT is_ai ORDER BY created_at",
            (league_id,),
        ).fetchall()
        return rows

    def get_gm_id_from_team_id(self, league_id: str, team_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT id FROM gms WHERE league_id = %s AND team_id = %s",
            (league_id, team_id),
        ).fetchone()
        return row["id"] if row else None

    def get_human_gm_for_team(self, league_id: str, team_id: str) -> str | None:
        """The id of the human GM running a team, or None if the AI runs it."""
        row = self.conn.execute(
            """SELECT id FROM gms
               WHERE league_id = %s AND team_id = %s AND NOT is_ai
                 AND fired_at IS NULL
               LIMIT 1""",
            (league_id, team_id),
        ).fetchone()
        return row["id"] if row else None

    def get_human_gm_teams(self, league_id: str) -> dict[str, str]:
        """Return {gm_id: team_id} for the human GMs in a league that have a team."""
        rows = self.conn.execute(
            "SELECT id, team_id FROM gms WHERE league_id = %s AND NOT is_ai AND team_id IS NOT NULL",
            (league_id,),
        ).fetchall()
        return {r["id"]: r["team_id"] for r in rows}

    def get_by_id(self, gm_id: str) -> dict | None:
        row = self.conn.execute("SELECT * FROM gms WHERE id = %s", (gm_id,)).fetchone()
        return dict(row) if row else None

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

    def next_commissioner(self, league_id: str, leaving_gm_id: str) -> str | None:
        """The human GM who has been in the league longest, other than the one
        leaving, or None if there is nobody left."""
        row = self.conn.execute(
            """SELECT id FROM gms
               WHERE league_id = %s AND id <> %s
                 AND NOT is_ai AND user_id IS NOT NULL AND fired_at IS NULL
               ORDER BY created_at, id LIMIT 1""",
            (league_id, leaving_gm_id),
        ).fetchone()
        return row["id"] if row else None

    def hand_team_to_ai(self, gm_id: str) -> None:
        """Turn a human GM into an AI one. The row keeps its team, so the
        team's draft picks and history stay attached to it."""
        self.conn.execute(
            """UPDATE gms SET is_ai = TRUE, user_id = NULL,
                   display_name = 'AI Manager', is_away = FALSE, ready_period = NULL
               WHERE id = %s""",
            (gm_id,),
        )
        self.conn.execute("DELETE FROM gm_notifications WHERE gm_id = %s", (gm_id,))

    def has_people(self, league_id: str) -> bool:
        """Whether any person can still open the league, fired GMs included."""
        return bool(
            self.conn.execute(
                "SELECT 1 FROM gms WHERE league_id = %s AND user_id IS NOT NULL LIMIT 1",
                (league_id,),
            ).fetchone()
        )

    def delete_gm(self, gm_id: str) -> None:
        self.conn.execute("DELETE FROM gms WHERE id = %s", (gm_id,))

    def get_users_leagues(self, user_id: str) -> list[dict]:
        """Fetch the user's leagues"""
        rows = self.conn.execute(
            """SELECT l.id, l.name, l.state, l.mode, l.created_at, l.join_code,
                      l.last_played_at, l.is_practice,
                      MAX(s.year) as current_year,
                      COUNT(DISTINCT ls.season_id) as season_number,
                      (l.commissioner_gm_id = g.id) as is_commissioner,
                      (SELECT COUNT(*) FROM gms o
                       WHERE o.league_id = l.id AND o.user_id IS NOT NULL) as people
            FROM leagues l
            JOIN gms g ON g.league_id = l.id
            LEFT JOIN league_seasons ls ON ls.league_id = l.id
            LEFT JOIN seasons s ON s.id = ls.season_id
            WHERE g.user_id = %s AND NOT g.is_ai
            GROUP BY l.id, l.name, l.state, l.mode, l.created_at, l.join_code,
                     l.last_played_at, l.is_practice, g.id
            ORDER BY l.created_at DESC""",
            (user_id,),
        ).fetchall()

        # Convert rows to plain dicts if your driver doesn't do it automatically
        return [dict(row) for row in rows]

    def get_public_leagues(self, user_id: str) -> list[dict]:
        """Public leagues the user isn't in. Leagues still in the lobby come
        first, since those can be joined, and finished ones last. Tutorial
        leagues never show here, even if an admin made one public."""
        rows = self.conn.execute(
            """SELECT l.id, l.name, l.state, l.mode, l.created_at,
                      l.last_played_at,
                      MAX(s.year) as current_year,
                      COUNT(DISTINCT ls.season_id) as season_number,
                      (SELECT COUNT(*) FROM gms o
                       WHERE o.league_id = l.id AND o.user_id IS NOT NULL) as people
            FROM leagues l
            LEFT JOIN league_seasons ls ON ls.league_id = l.id
            LEFT JOIN seasons s ON s.id = ls.season_id
            WHERE l.is_public AND NOT l.is_practice
              AND NOT EXISTS (SELECT 1 FROM gms m
                              WHERE m.league_id = l.id AND m.user_id = %s)
            GROUP BY l.id, l.name, l.state, l.mode, l.created_at, l.last_played_at
            ORDER BY (l.state = 'lobby') DESC, (l.state = 'complete'),
                     l.created_at DESC""",
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_profile(self, gm_id: str) -> dict | None:
        """Return the gm_profiles row for a GM, or None."""
        row = self.conn.execute(
            "SELECT * FROM gm_profiles WHERE gm_id = %s", (gm_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_team_profile(self, team_id: str, league_id: str) -> dict | None:
        """The gm_profiles row of whoever runs this team, person or AI. None
        if the team has no GM."""
        row = self.conn.execute(
            """SELECT gp.* FROM gms g
               JOIN gm_profiles gp ON gp.gm_id = g.id
               WHERE g.team_id = %s AND g.league_id = %s AND g.fired_at IS NULL
               ORDER BY g.is_ai LIMIT 1""",
            (team_id, league_id),
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

    def assign_team_to_gm(self, team_id: str, gm_id: str) -> None:
        self.conn.execute(
            "UPDATE gms SET team_id = %s WHERE id = %s",
            (
                team_id,
                gm_id,
            ),
        )

    def get_human_gm_city_mascot(self, league_id: str) -> dict:
        row = self.conn.execute(
            """
            SELECT t.city, t.mascot FROM gms g
            JOIN teams t ON t.id = g.team_id
            WHERE g.league_id = %s AND NOT g.is_ai
            LIMIT 1
            """,
            (league_id,),
        ).fetchone()
        return dict(row)
