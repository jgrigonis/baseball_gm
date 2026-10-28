# src/db/repositories/team_state_repo.py
#
# team_states: each team's state at each checkpoint (src/league/team_state.py).

from __future__ import annotations

from psycopg.types.json import Jsonb


class TeamStateRepository:
    def __init__(self, conn):
        self.conn = conn

    def add(
        self,
        league_id: str,
        season_id: str,
        team_id: str,
        as_of: str,
        state: str,
        held: int,
        candidate: str,
        inputs: dict,
    ) -> None:
        self.conn.execute(
            """INSERT INTO team_states
               (league_id, season_id, team_id, as_of, state, held, candidate, inputs)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                league_id,
                season_id,
                team_id,
                as_of,
                state,
                held,
                candidate,
                Jsonb(inputs),
            ),
        )

    def latest(self, league_id: str, season_id: str) -> dict[str, dict]:
        """Each team's latest row this season, by team id."""
        rows = self.conn.execute(
            """SELECT DISTINCT ON (team_id) *
               FROM team_states WHERE league_id = %s AND season_id = %s
               ORDER BY team_id, id DESC""",
            (league_id, season_id),
        ).fetchall()
        return {r["team_id"]: dict(r) for r in rows}

    def last_checkpoint(self, league_id: str, season_id: str) -> str | None:
        """The league date of the latest checkpoint this season."""
        row = self.conn.execute(
            """SELECT MAX(as_of) AS as_of FROM team_states
               WHERE league_id = %s AND season_id = %s""",
            (league_id, season_id),
        ).fetchone()
        return row["as_of"] if row else None

    def history(self, team_id: str, season_id: str) -> list[dict]:
        """A team's states this season, oldest first."""
        rows = self.conn.execute(
            """SELECT as_of, state, held, candidate FROM team_states
               WHERE team_id = %s AND season_id = %s ORDER BY id""",
            (team_id, season_id),
        ).fetchall()
        return [dict(r) for r in rows]
