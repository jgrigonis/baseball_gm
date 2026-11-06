# src/db/repositories/waiver_repo.py
"""
Waivers (src/api/services/waivers.py).

Uses tables:
- waivers        one row per released 40-man player: who let him go, when he
                 clears, and how it ended (claimed or cleared)
- waiver_claims  the teams that claimed him
"""

from __future__ import annotations


class WaiverRepository:
    def __init__(self, conn):
        self.conn = conn

    def place(
        self,
        league_id: str,
        player_id: str,
        from_team_id: str,
        placed_on: str,
        clears_on: str | None,
    ) -> int:
        row = self.conn.execute(
            """INSERT INTO waivers (league_id, player_id, from_team_id,
                                    placed_on, clears_on)
               VALUES (%s, %s, %s, %s, %s) RETURNING id""",
            (league_id, player_id, from_team_id, placed_on, clears_on),
        ).fetchone()
        return row["id"]

    def open_for(self, league_id: str) -> list[dict]:
        rows = self.conn.execute(
            """SELECT * FROM waivers WHERE league_id = %s AND status = 'open'
               ORDER BY id""",
            (league_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def open_for_player(self, player_id: str) -> dict | None:
        row = self.conn.execute(
            """SELECT * FROM waivers WHERE player_id = %s AND status = 'open'
               ORDER BY id DESC LIMIT 1""",
            (player_id,),
        ).fetchone()
        return dict(row) if row else None

    def due(self, league_id: str, today: str) -> list[dict]:
        """Open waivers that clear after today's games (or earlier)."""
        rows = self.conn.execute(
            """SELECT * FROM waivers
               WHERE league_id = %s AND status = 'open'
                 AND clears_on IS NOT NULL AND clears_on <= %s
               ORDER BY id""",
            (league_id, today),
        ).fetchall()
        return [dict(r) for r in rows]

    def claim(self, waiver_id: int, team_id: str) -> None:
        self.conn.execute(
            """INSERT INTO waiver_claims (waiver_id, team_id) VALUES (%s, %s)
               ON CONFLICT DO NOTHING""",
            (waiver_id, team_id),
        )

    def withdraw(self, waiver_id: int, team_id: str) -> None:
        self.conn.execute(
            "DELETE FROM waiver_claims WHERE waiver_id = %s AND team_id = %s",
            (waiver_id, team_id),
        )

    def claimants(self, waiver_id: int) -> list[str]:
        rows = self.conn.execute(
            "SELECT team_id FROM waiver_claims WHERE waiver_id = %s",
            (waiver_id,),
        ).fetchall()
        return [r["team_id"] for r in rows]

    def claims_by(self, league_id: str, team_id: str) -> set[str]:
        """Players the team has claimed on open waivers."""
        rows = self.conn.execute(
            """SELECT w.player_id FROM waiver_claims c
               JOIN waivers w ON w.id = c.waiver_id
               WHERE w.league_id = %s AND w.status = 'open' AND c.team_id = %s""",
            (league_id, team_id),
        ).fetchall()
        return {r["player_id"] for r in rows}

    def close(self, waiver_id: int, claimed_by: str | None) -> None:
        self.conn.execute(
            "UPDATE waivers SET status = %s, claimed_by = %s WHERE id = %s",
            ("claimed" if claimed_by else "cleared", claimed_by, waiver_id),
        )
