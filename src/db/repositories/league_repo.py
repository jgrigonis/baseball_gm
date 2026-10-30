# src/db/repositories/league_repo.py
import uuid


class LeagueRepository:
    """
    Repository for managing leagues, seasons, and team assignments.

    Typical workflow:
    1. get_or_create_by_name() - Create or get existing league
    2. assign_season_to_league() - Link season to league
    3. assign_team_to_league() - Add teams to league for that season
    """

    def __init__(self, conn):
        self.conn = conn

    def create_new_league(
        self,
        league_id: str,
        name: str,
        join_code: str,
        mode: str,
        commissioner_gm_id: str,
        settings: dict,
    ) -> None:
        """Strict creation of a new league with full settings."""
        self.conn.execute(
            """INSERT INTO leagues
                (id, name, join_code, mode, num_teams, decision_window_sec,
                draft_window_sec, lineup_window_sec, reentry_enabled, pace_control,
                sim_period_days, num_seasons, is_public, is_practice, trade_vote,
                pick_trades, state, commissioner_gm_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, 'lobby', NULL)""",
            (
                league_id,
                name,
                join_code,
                mode,
                settings.get("num_teams", 30),
                settings.get("decision_window_sec", 120),
                settings.get("draft_window_sec", 300),
                settings.get("lineup_window_sec", 600),
                settings.get("reentry_enabled", True),
                settings.get("pace_control", "timer"),
                settings.get("sim_period_days", 3),
                settings.get("num_seasons", 10),
                settings.get("is_public", False),
                settings.get("is_practice", False),
                settings.get("trade_vote", True),
                settings.get("pick_trades", False),
            ),
        )

    def get_by_join_code(self, code: str) -> dict | None:
        row = self.conn.execute(
            "SELECT id, name, state FROM leagues WHERE join_code = %s", (code,)
        ).fetchone()
        return dict(row) if row else None

    def get_by_id(self, league_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM leagues WHERE id = %s", (league_id,)
        ).fetchone()
        return dict(row) if row else None

    # was create_league
    def get_or_create_by_name(self, name: str, league_id: str | None = None) -> str:
        """
        Create a league or return existing league ID if name already exists.

        Args:
            name: League name (e.g., "MLB", "Minor League A")
            league_id: if you provide a league_id, it will create that league
                if it doesn't exist.
                If you don't provide a league_id, it will create a new league
                if the name doesn't already exist.
                If it finds an existing league, it will just return that id

        Returns:
            League ID (UUID hex string)
        """
        if league_id:
            existing = self._get_league_id_by_id(league_id)
            if existing:
                return existing
        else:
            # Check if league name already exists
            existing = self._get_league_id_by_name(name)
            if existing:
                return existing

        # Create new league id if none provided
        if league_id is None:
            league_id = uuid.uuid4().hex
        self.conn.execute(
            "INSERT INTO leagues (id, name) VALUES (%s, %s)", (league_id, name)
        )
        # self.conn.commit()
        return league_id

    def _get_league_id_by_name(self, name: str) -> str | None:
        """Helper: Get league ID by name."""
        row = self.conn.execute(
            "SELECT id FROM leagues WHERE name = %s", (name,)
        ).fetchone()

        return row["id"] if row else None

    def _get_league_id_by_id(self, league_id: str) -> str | None:
        """Helper: Get league ID by ID."""
        row = self.conn.execute(
            "SELECT id FROM leagues WHERE id = %s", (league_id,)
        ).fetchone()

        return row["id"] if row else None

    def assign_season_to_league(self, league_id: str, season_id: str) -> None:
        """
        Register a season as part of a league.
        Idempotent - safe to call multiple times.

        Args:
            league_id: League ID
            season_id: Season ID
        """
        self.conn.execute(
            """
            INSERT INTO league_seasons (league_id, season_id)
            VALUES (%s, %s)
            ON CONFLICT DO NOTHING
            """,
            (league_id, season_id),
        )
        # self.conn.commit()

    def assign_team_to_league(
        self, league_id: str, season_id: str, team_id: str
    ) -> None:
        """
        Assign a team to a league for a specific season.
        Idempotent - safe to call multiple times.

        Args:
            league_id: League ID
            season_id: Season ID
            team_id: Team ID

        Note:
            Must call assign_season_to_league() first to satisfy foreign key constraint.
        """
        self.conn.execute(
            """
            INSERT INTO league_season_teams (league_id, season_id, team_id)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            (league_id, season_id, team_id),
        )
        # self.conn.commit()

    def has_season(self, league_id: str, season_id: str) -> bool:
        """
        Check if a season is assigned to a league.

        Args:
            league_id: League ID
            season_id: Season ID

        Returns:
            True if season is assigned to league, False otherwise
        """
        row = self.conn.execute(
            """
            SELECT 1 FROM league_seasons
            WHERE league_id = %s AND season_id = %s
            """,
            (league_id, season_id),
        ).fetchone()

        return row is not None

    def count_seasons(self, league_id: str) -> int:
        """How many seasons the league has started, the current one included."""
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM league_seasons WHERE league_id = %s",
            (league_id,),
        ).fetchone()
        return row["n"]

    def get_league_teams(self, league_id: str, season_id: str) -> list[str]:
        """
        Get all team IDs in a league for a specific season.

        Args:
            league_id: League ID
            season_id: Season ID

        Returns:
            List of team IDs
        """
        rows = self.conn.execute(
            """
            SELECT team_id FROM league_season_teams
            WHERE league_id = %s AND season_id = %s
            ORDER BY team_id
            """,
            (league_id, season_id),
        ).fetchall()

        return [row["team_id"] for row in rows]

    def get_state(self, league_id: str) -> str:
        """
        Return the state of the league
        """
        league_state = self.conn.execute(
            "SELECT state FROM leagues WHERE id = %s", (league_id,)
        ).fetchone()["state"]
        return league_state

    def get_league_id_from_season_id(self, season_id: str) -> str:
        """
        Get the league_id from league_seasons based on the season_id
        """
        league_row = self.conn.execute(
            "SELECT league_id FROM league_seasons WHERE season_id = %s LIMIT 1",
            (season_id,),
        ).fetchone()
        league_id = league_row["league_id"] if league_row else ""
        return league_id

    def rename(self, league_id: str, new_name: str) -> None:
        """Rename a league. Caller must verify commissioner before calling."""
        self.conn.execute(
            "UPDATE leagues SET name = %s WHERE id = %s",
            (new_name.strip(), league_id),
        )

    def delete(self, league_id: str) -> None:
        """Delete a league and everything it owns: GMs, drafts, seasons (and
        with them games and stats), teams and players.

        Seasons and teams are only deleted when no other league uses them.
        Players belong to the league that created them (players.league_id),
        plus anyone on one of its teams who isn't tagged to another league.
        """
        season_ids = self._column(
            """SELECT season_id AS id FROM league_seasons ls
               WHERE league_id = %s AND NOT EXISTS (
                   SELECT 1 FROM league_seasons o
                   WHERE o.season_id = ls.season_id AND o.league_id <> %s)""",
            (league_id, league_id),
        )
        team_ids = self._column(
            """SELECT DISTINCT team_id AS id FROM league_season_teams lst
               WHERE league_id = %s AND NOT EXISTS (
                   SELECT 1 FROM league_season_teams o
                   WHERE o.team_id = lst.team_id AND o.league_id <> %s)""",
            (league_id, league_id),
        )
        player_ids = self._column(
            """SELECT id FROM players WHERE league_id = %s
               UNION
               SELECT p.id FROM players p
               JOIN team_players tp ON tp.player_id = p.id
               WHERE tp.team_id = ANY(%s)
                 AND (p.league_id IS NULL OR p.league_id = %s)""",
            (league_id, team_ids, league_id),
        )

        # Per-league player state, keyed by league_id with no foreign key.
        for table in ("pitcher_state", "player_energy", "player_injuries"):
            self.conn.execute(f"DELETE FROM {table} WHERE league_id = %s", (league_id,))
        # Cascades to GMs, drafts and their picks, pick rights, retirements and
        # the league's season and team links.
        self.conn.execute("DELETE FROM leagues WHERE id = %s", (league_id,))
        # Cascades to games and their stats, series and offseason steps.
        self.conn.execute("DELETE FROM seasons WHERE id = ANY(%s)", (season_ids,))
        # Cascades to rosters, rotations and bullpen roles.
        self.conn.execute("DELETE FROM teams WHERE id = ANY(%s)", (team_ids,))
        # Cascades to skills, status, caps, season stats and the injury log.
        self.conn.execute("DELETE FROM players WHERE id = ANY(%s)", (player_ids,))

    def _column(self, sql: str, params: tuple) -> list[str]:
        return [r["id"] for r in self.conn.execute(sql, params).fetchall()]

    def get_league_mode(self, league_id: str) -> str:
        """Get the mode of the league."""
        if league_id is None:
            return "blitz"
        row = self.conn.execute(
            "SELECT mode FROM leagues WHERE id = %s", (league_id,)
        ).fetchone()
        if row:
            return dict(row).get("mode", "blitz")
        else:
            return "blitz"

    def list_all(self) -> list[dict]:
        """Return all leagues ordered by creation time (id, name, state)."""
        rows = self.conn.execute(
            "SELECT id, name, state FROM leagues ORDER BY created_at"
        ).fetchall()
        return [dict(r) for r in rows]

    # Settings an admin can change (see src/api/services/admin.py).
    EDITABLE_SETTINGS = (
        "name",
        "mode",
        "pace_control",
        "decision_window_sec",
        "draft_window_sec",
        "lineup_window_sec",
        "sim_period_days",
        "num_seasons",
        "reentry_enabled",
        "is_public",
    )

    def update_settings(self, league_id: str, settings: dict) -> None:
        cols = [c for c in self.EDITABLE_SETTINGS if c in settings]
        set_clause = ", ".join(f"{c} = %s" for c in cols)
        self.conn.execute(
            f"UPDATE leagues SET {set_clause} WHERE id = %s",
            [*(settings[c] for c in cols), league_id],
        )

    def set_stop_for_trade_offers(self, league_id: str, on: bool) -> None:
        self.conn.execute(
            "UPDATE leagues SET stop_for_trade_offers = %s WHERE id = %s",
            (on, league_id),
        )

    def set_paused(self, league_id: str, paused: bool) -> None:
        self.conn.execute(
            "UPDATE leagues SET is_paused = %s WHERE id = %s", (paused, league_id)
        )

    def list_for_admin(self) -> list[dict]:
        """Every league with all its settings, its season count, its current
        season's id, and how many people are in it, newest first."""
        rows = self.conn.execute(
            """SELECT l.*,
                      (SELECT COUNT(*) FROM league_seasons ls
                       WHERE ls.league_id = l.id) AS season_number,
                      (SELECT s.id FROM seasons s
                       JOIN league_seasons ls ON ls.season_id = s.id
                       WHERE ls.league_id = l.id
                       ORDER BY s.year DESC LIMIT 1) AS season_id,
                      (SELECT COUNT(*) FROM gms g
                       WHERE g.league_id = l.id AND g.user_id IS NOT NULL) AS people,
                      (SELECT g.display_name FROM gms g
                       WHERE g.id = l.commissioner_gm_id) AS commissioner_name
               FROM leagues l
               ORDER BY l.created_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_played(self, league_id: str) -> None:
        """Record that the league was just played (shown on the leagues page)."""
        self.conn.execute(
            "UPDATE leagues SET last_played_at = NOW() WHERE id = %s", (league_id,)
        )

    def set_state(self, league_id: str, state: str) -> None:
        """Set the league to state: state. Moving on counts as playing."""
        self.conn.execute(
            "UPDATE leagues SET state = %s, last_played_at = NOW() WHERE id = %s",
            (
                state,
                league_id,
            ),
        )

    def mark_coach_step(self, league_id: str, step: str) -> None:
        """Record that the GM did one of the coach's steps. Only tutorial
        leagues have a coach, so this does nothing in any other league."""
        self.conn.execute(
            """UPDATE leagues SET coach_done = array_append(coach_done, %s)
               WHERE id = %s AND is_practice AND NOT (%s = ANY(coach_done))""",
            (step, league_id, step),
        )

    def draft_complete(self, league_id: str) -> bool:
        """Return True if the draft is complete, else False."""
        row = self.conn.execute(
            """SELECT d.state FROM drafts d
            JOIN league_seasons ls ON ls.season_id = d.season_id
            JOIN seasons s ON s.id = ls.season_id
            WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
        return bool(row and row["state"] == "complete")

    def progress(self, league_id: str) -> dict | None:
        """How far the league has got: its state, its ready-check period and
        the games played across all its seasons. Any of these changes when
        the league moves on, however it was moved."""
        row = self.conn.execute(
            """SELECT l.state, l.sim_period,
                      (SELECT COUNT(*) FROM games g
                         JOIN league_seasons ls ON ls.season_id = g.season_id
                        WHERE ls.league_id = l.id AND g.completed = 1)
                      AS games_played
               FROM leagues l WHERE l.id = %s""",
            (league_id,),
        ).fetchone()
        return dict(row) if row else None
