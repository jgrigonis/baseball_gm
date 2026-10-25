# src/db/repositories/ready_check_repo.py


class ReadyCheckRepository:
    """Who has to be ready before a multiplayer league sims its next period,
    who is, and when the Decision Window ends."""

    # Human GMs still running a team. Away GMs are counted separately: they
    # don't hold the league up.
    _HUMAN = "league_id = %s AND NOT is_ai AND user_id IS NOT NULL AND fired_at IS NULL"

    def __init__(self, conn):
        self.conn = conn

    def human_gm_count(self, league_id: str) -> int:
        return self.conn.execute(
            f"SELECT COUNT(*) AS n FROM gms WHERE {self._HUMAN}", (league_id,)
        ).fetchone()["n"]

    def period(self, league_id: str) -> dict | None:
        """The league's state, pace, current period and the seconds left in its
        Decision Window (negative once it has run out; None with no window)."""
        row = self.conn.execute(
            """SELECT state, pace_control, decision_window_sec, sim_period,
                      sim_period_days, period_deadline,
                      EXTRACT(EPOCH FROM period_deadline - NOW()) AS seconds_left
               FROM leagues WHERE id = %s""",
            (league_id,),
        ).fetchone()
        return dict(row) if row else None

    def gms(self, league_id: str) -> list[dict]:
        """The human GMs with whether each is away and ready for this period."""
        rows = self.conn.execute(
            """SELECT g.id, g.display_name, g.is_away,
                       g.ready_period IS NOT DISTINCT FROM l.sim_period AS ready
                FROM gms g JOIN leagues l ON l.id = g.league_id
                WHERE g.league_id = %s AND NOT g.is_ai
                  AND g.user_id IS NOT NULL AND g.fired_at IS NULL
                ORDER BY g.created_at""",
            (league_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def set_ready(self, gm_id: str, ready: bool) -> None:
        self.conn.execute(
            """UPDATE gms SET ready_period = CASE WHEN %s THEN
                   (SELECT sim_period FROM leagues WHERE id = gms.league_id)
               END
               WHERE id = %s""",
            (ready, gm_id),
        )

    def set_away(self, gm_id: str, away: bool) -> None:
        self.conn.execute("UPDATE gms SET is_away = %s WHERE id = %s", (away, gm_id))

    def open_window(self, league_id: str) -> None:
        """Start the Decision Window for the current period now."""
        self.conn.execute(
            """UPDATE leagues
               SET period_deadline = NOW() + decision_window_sec * INTERVAL '1 second'
               WHERE id = %s""",
            (league_id,),
        )

    def next_period(self, league_id: str) -> None:
        """Move to the next period: everyone becomes un-ready, and under timer
        pace its Decision Window starts now."""
        self.conn.execute(
            """UPDATE leagues SET sim_period = sim_period + 1,
                   period_deadline = CASE WHEN pace_control = 'timer'
                       THEN NOW() + decision_window_sec * INTERVAL '1 second'
                   END
               WHERE id = %s""",
            (league_id,),
        )
