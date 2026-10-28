# src/db/repositories/ready_check_repo.py


class ReadyCheckRepository:
    """Who has to be ready before a multiplayer league sims its next period,
    who is, and when the period's window ends."""

    # Human GMs still running a team. Away GMs are counted separately: they
    # don't hold the league up.
    _HUMAN = "league_id = %s AND NOT is_ai AND user_id IS NOT NULL AND fired_at IS NULL"

    # Seconds in the current period's window: the draft gets the Draft Window,
    # the preseason period (setting the first lineup) the Lineup Window, and
    # every other period the Decision Window. Read after the period has run,
    # so it times the period that is starting.
    _WINDOW = """CASE state
                     WHEN 'draft' THEN draft_window_sec
                     WHEN 'preseason' THEN lineup_window_sec
                     ELSE decision_window_sec
                 END"""

    def __init__(self, conn):
        self.conn = conn

    def human_gm_count(self, league_id: str) -> int:
        return self.conn.execute(
            f"SELECT COUNT(*) AS n FROM gms WHERE {self._HUMAN}", (league_id,)
        ).fetchone()["n"]

    def period(self, league_id: str) -> dict | None:
        """The league's state, pace, current period and the seconds left in its
        window (negative once it has run out; None with no window)."""
        row = self.conn.execute(
            """SELECT state, mode, pace_control, decision_window_sec, sim_period, is_paused,
                      sim_period_days, period_deadline,
                      EXTRACT(EPOCH FROM period_deadline - NOW()) AS seconds_left
               FROM leagues WHERE id = %s""",
            (league_id,),
        ).fetchone()
        return dict(row) if row else None

    def gms(self, league_id: str) -> list[dict]:
        """The human GMs with whether each is away and ready for this period."""
        rows = self.conn.execute(
            """SELECT g.id, g.team_id, g.display_name, g.is_away,
                       g.ready_period IS NOT DISTINCT FROM l.sim_period AS ready
                FROM gms g JOIN leagues l ON l.id = g.league_id
                WHERE g.league_id = %s AND NOT g.is_ai
                  AND g.user_id IS NOT NULL AND g.fired_at IS NULL
                ORDER BY g.created_at, g.display_name""",
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
        """Start the current period's window now."""
        self.conn.execute(
            f"""UPDATE leagues
               SET period_deadline = NOW() + ({self._WINDOW}) * INTERVAL '1 second'
               WHERE id = %s""",
            (league_id,),
        )

    def next_period(self, league_id: str, window_multiplier: int = 1) -> None:
        """Move to the next period: everyone becomes un-ready, and under timer
        pace its window starts now, window_multiplier times as long as usual
        (the trade deadline gets a longer one)."""
        self.conn.execute(
            f"""UPDATE leagues SET sim_period = sim_period + 1,
                   period_deadline = CASE WHEN pace_control = 'timer'
                       THEN NOW() + ({self._WINDOW}) * %s * INTERVAL '1 second'
                   END
               WHERE id = %s""",
            (window_multiplier, league_id),
        )
