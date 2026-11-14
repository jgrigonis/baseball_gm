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

    def take_over_team(
        self, gm_id: str, user_id: str, display_name: str, joined_year: int
    ) -> None:
        """Turn an AI GM into a person who has taken over its team: the
        reverse of hand_team_to_ai. They start out like someone new to the
        league, so they get the welcome screen and the getting-started bar."""
        self.conn.execute(
            """UPDATE gms SET is_ai = FALSE, user_id = %s, display_name = %s,
                   persona_id = NULL, is_away = FALSE, ready_period = NULL,
                   welcomed_at = NULL, welcomed_season_id = NULL,
                   roster_saved_at = NULL,
                   seen_at = NULL, alerted_at = NULL, joined_year = %s
               WHERE id = %s AND is_ai""",
            (user_id, display_name, joined_year, gm_id),
        )

    def has_people(self, league_id: str, besides_gm_id: str | None = None) -> bool:
        """Whether any person can still open the league, fired GMs included,
        not counting `besides_gm_id`."""
        return bool(
            self.conn.execute(
                """SELECT 1 FROM gms
                   WHERE league_id = %s AND user_id IS NOT NULL
                     AND id IS DISTINCT FROM %s
                   LIMIT 1""",
                (league_id, besides_gm_id),
            ).fetchone()
        )

    def delete_gm(self, gm_id: str) -> None:
        self.conn.execute("DELETE FROM gms WHERE id = %s", (gm_id,))

    def get_users_leagues(self, user_id: str) -> list[dict]:
        """Fetch the user's leagues, with the team they run in each (team_city
        and team_mascot, None until they have one)."""
        rows = self.conn.execute(
            """SELECT l.id, l.name, l.state, l.mode, l.created_at, l.join_code,
                      l.last_played_at, l.is_practice,
                      t.city as team_city, t.mascot as team_mascot,
                      MAX(s.year) as current_year,
                      COUNT(DISTINCT ls.season_id) FILTER (WHERE NOT s.is_backstory)
                          as season_number,
                      (l.commissioner_gm_id = g.id) as is_commissioner,
                      (g.fired_at IS NOT NULL) as fired,
                      (SELECT COUNT(*) FROM gms o
                       WHERE o.league_id = l.id AND o.user_id IS NOT NULL) as people
            FROM leagues l
            JOIN gms g ON g.league_id = l.id
            LEFT JOIN teams t ON t.id = g.team_id
            LEFT JOIN league_seasons ls ON ls.league_id = l.id
            LEFT JOIN seasons s ON s.id = ls.season_id
            WHERE g.user_id = %s AND NOT g.is_ai
            GROUP BY l.id, l.name, l.state, l.mode, l.created_at, l.join_code,
                     l.last_played_at, l.is_practice, g.id, t.city, t.mascot
            ORDER BY l.created_at DESC""",
            (user_id,),
        ).fetchall()

        # Convert rows to plain dicts if your driver doesn't do it automatically
        return [dict(row) for row in rows]

    def get_public_leagues(self, user_id: str) -> list[dict]:
        """Public leagues the user isn't in, and private ones they entered the
        join code of (league_watchers). Leagues still in the lobby come first,
        since those can be joined, and finished ones last. Tutorial leagues
        never show here, even if an admin made one public."""
        rows = self.conn.execute(
            """SELECT l.id, l.name, l.state, l.mode, l.created_at,
                      l.last_played_at, l.late_joins, l.is_practice,
                      MAX(s.year) as current_year,
                      COUNT(DISTINCT ls.season_id) FILTER (WHERE NOT s.is_backstory)
                          as season_number,
                      (SELECT COUNT(*) FROM gms o
                       WHERE o.league_id = l.id AND o.user_id IS NOT NULL) as people
            FROM leagues l
            LEFT JOIN league_seasons ls ON ls.league_id = l.id
            LEFT JOIN seasons s ON s.id = ls.season_id
            WHERE (l.is_public
                   OR EXISTS (SELECT 1 FROM league_watchers w
                              WHERE w.league_id = l.id AND w.user_id = %s))
              AND NOT l.is_practice
              AND NOT EXISTS (SELECT 1 FROM gms m
                              WHERE m.league_id = l.id AND m.user_id = %s)
            GROUP BY l.id, l.name, l.state, l.mode, l.created_at, l.last_played_at,
                     l.late_joins, l.is_practice
            ORDER BY (l.state = 'lobby') DESC, (l.state = 'complete'),
                     l.created_at DESC""",
            (user_id, user_id),
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

    def pitcher_leashes(self, team_id: str) -> dict[str, str]:
        """{player_id: pitches} for the team's starters with their own leash."""
        rows = self.conn.execute(
            "SELECT player_id, pitches FROM pitcher_leashes WHERE team_id = %s",
            (team_id,),
        ).fetchall()
        return {r["player_id"]: r["pitches"] for r in rows}

    def set_pitcher_leash(
        self, team_id: str, player_id: str, pitches: str | None
    ) -> None:
        """Give a starter his own leash, or (None) put him back on the team's."""
        if pitches is None:
            self.conn.execute(
                "DELETE FROM pitcher_leashes WHERE team_id = %s AND player_id = %s",
                (team_id, player_id),
            )
            return
        self.conn.execute(
            """INSERT INTO pitcher_leashes (team_id, player_id, pitches)
               VALUES (%s, %s, %s)
               ON CONFLICT (team_id, player_id) DO UPDATE SET pitches = EXCLUDED.pitches""",
            (team_id, player_id, pitches),
        )

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

    def needs_welcome(self, gm_id: str, season_id: str) -> bool:
        """True until the GM has seen the welcome screen (the season preview
        after the first season) for this season."""
        row = self.conn.execute(
            "SELECT welcomed_season_id FROM gms WHERE id = %s AND NOT is_ai", (gm_id,)
        ).fetchone()
        return bool(row) and row["welcomed_season_id"] != season_id

    def mark_welcomed(self, gm_id: str, season_id: str | None = None) -> None:
        """The GM has seen this season's welcome screen: by default their
        league's newest season."""
        self.conn.execute(
            """UPDATE gms SET welcomed_at = COALESCE(welcomed_at, NOW()),
                   welcomed_season_id = COALESCE(%s, (
                       SELECT s.id FROM seasons s
                       JOIN league_seasons ls ON ls.season_id = s.id
                       WHERE ls.league_id = gms.league_id
                       ORDER BY s.year DESC LIMIT 1))
               WHERE id = %s""",
            (season_id, gm_id),
        )

    def summary_seen(self, gm_id: str, season_id: str) -> bool:
        """True once the GM has opened this season's summary."""
        row = self.conn.execute(
            "SELECT summary_seen_season_id FROM gms WHERE id = %s", (gm_id,)
        ).fetchone()
        return bool(row) and row["summary_seen_season_id"] == season_id

    def mark_summary_seen(self, gm_id: str, season_id: str) -> None:
        self.conn.execute(
            "UPDATE gms SET summary_seen_season_id = %s WHERE id = %s",
            (season_id, gm_id),
        )

    def expiring_seen(self, gm_id: str, season_id: str) -> bool:
        """True once the GM has opened the Expiring Deals tab in this
        season's offseason."""
        row = self.conn.execute(
            "SELECT expiring_seen_season_id FROM gms WHERE id = %s", (gm_id,)
        ).fetchone()
        return bool(row) and row["expiring_seen_season_id"] == season_id

    def mark_expiring_seen(self, gm_id: str, season_id: str) -> None:
        self.conn.execute(
            "UPDATE gms SET expiring_seen_season_id = %s WHERE id = %s",
            (season_id, gm_id),
        )

    PRESEASON_TABS = {
        "roster": "roster_seen_season_id",
        "lineup": "lineup_seen_season_id",
        "strategy": "strategy_seen_season_id",
    }

    def preseason_seen(self, gm_id: str, season_id: str) -> set[str]:
        """The preseason tabs (roster, lineup, strategy) the GM has opened
        before this season's Opening Day."""
        row = self.conn.execute(
            "SELECT roster_seen_season_id, lineup_seen_season_id,"
            " strategy_seen_season_id FROM gms WHERE id = %s",
            (gm_id,),
        ).fetchone()
        if not row:
            return set()
        return {
            tab for tab, col in self.PRESEASON_TABS.items() if row[col] == season_id
        }

    def mark_preseason_seen(self, gm_id: str, season_id: str, tab: str) -> None:
        col = self.PRESEASON_TABS[tab]
        self.conn.execute(
            f"UPDATE gms SET {col} = %s WHERE id = %s", (season_id, gm_id)
        )

    # A multiplayer preseason's Roster and Lineup pills go once the GM saves
    # each (Josh, 2026-11-14), not just opens it.
    PRESEASON_SAVES = {
        "roster": "roster_saved_season_id",
        "lineup": "lineup_saved_season_id",
    }

    def preseason_saved(self, gm_id: str, season_id: str) -> set[str]:
        """The preseason tabs (roster, lineup) the GM has saved this
        preseason."""
        row = self.conn.execute(
            "SELECT roster_saved_season_id, lineup_saved_season_id FROM gms"
            " WHERE id = %s",
            (gm_id,),
        ).fetchone()
        if not row:
            return set()
        return {
            tab for tab, col in self.PRESEASON_SAVES.items() if row[col] == season_id
        }

    def mark_preseason_saved(self, league_id: str, gm_id: str, tab: str) -> None:
        """The GM saved the Roster or Lineup. Counts only in the preseason,
        for the league's newest season (the one about to start)."""
        col = self.PRESEASON_SAVES[tab]
        self.conn.execute(
            f"""UPDATE gms SET {col} = (
                    SELECT s.id FROM seasons s
                    JOIN league_seasons ls ON ls.season_id = s.id
                    WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1)
                WHERE id = %s
                  AND EXISTS (SELECT 1 FROM leagues
                              WHERE id = %s AND state = 'preseason')""",
            (league_id, gm_id, league_id),
        )

    # The draft's tabs (a multiplayer draft's pills, web/utils.py): the
    # column holding the season whose draft the GM opened each in.
    DRAFT_TABS = {
        "draft": "draft_tab_seen_season_id",
        "free-agents": "fa_tab_seen_season_id",
    }

    def draft_seen(self, gm_id: str, season_id: str) -> set[str]:
        """The draft tabs (draft, free-agents) the GM has opened during this
        draft. season_id is the league shell's season while drafting."""
        row = self.conn.execute(
            "SELECT draft_tab_seen_season_id, fa_tab_seen_season_id FROM gms"
            " WHERE id = %s",
            (gm_id,),
        ).fetchone()
        if not row:
            return set()
        return {tab for tab, col in self.DRAFT_TABS.items() if row[col] == season_id}

    def mark_draft_seen(self, gm_id: str, season_id: str, tab: str) -> None:
        col = self.DRAFT_TABS[tab]
        self.conn.execute(
            f"UPDATE gms SET {col} = %s WHERE id = %s", (season_id, gm_id)
        )

    def mark_trade_roster_due(self, gm_id: str, season_id: str) -> None:
        """A trade brought this GM players, who wait in the organization
        until they're moved to the 40-man."""
        self.conn.execute(
            "UPDATE gms SET trade_roster_season_id = %s WHERE id = %s",
            (season_id, gm_id),
        )

    def trade_roster_due(self, gm_id: str, season_id: str) -> bool:
        row = self.conn.execute(
            "SELECT trade_roster_season_id FROM gms WHERE id = %s", (gm_id,)
        ).fetchone()
        return bool(row) and row["trade_roster_season_id"] == season_id

    def clear_trade_roster_due(self, gm_id: str) -> None:
        self.conn.execute(
            "UPDATE gms SET trade_roster_season_id = NULL"
            " WHERE id = %s AND trade_roster_season_id IS NOT NULL",
            (gm_id,),
        )

    def needs_setup_bar(self, gm_id: str) -> bool:
        """True until the GM first saves their roster."""
        row = self.conn.execute(
            "SELECT roster_saved_at FROM gms WHERE id = %s AND NOT is_ai", (gm_id,)
        ).fetchone()
        return bool(row) and row["roster_saved_at"] is None

    def mark_roster_saved(self, gm_id: str) -> None:
        self.conn.execute(
            "UPDATE gms SET roster_saved_at = NOW()"
            " WHERE id = %s AND roster_saved_at IS NULL",
            (gm_id,),
        )
