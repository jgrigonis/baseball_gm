# src/db/repositories/draft_repo.py


class DraftRepository:
    def __init__(self, conn):
        self.conn = conn

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_current_for_league(self, league_id: str) -> dict | None:
        """Return the most recent draft row for a league, or None."""
        row = self.conn.execute(
            """SELECT d.* FROM drafts d
               JOIN league_seasons ls ON ls.season_id = d.season_id
               JOIN seasons s ON s.id = ls.season_id
               WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_picked_ids(self, draft_id: str) -> set[str]:
        """Return the set of player_ids already picked in a draft."""
        rows = self.conn.execute(
            "SELECT player_id FROM draft_picks WHERE draft_id = %s",
            (draft_id,),
        ).fetchall()
        return {r["player_id"] for r in rows}

    def get_prospects(self, league_id: str) -> list[dict]:
        """Return all prospect players for a league, ordered by name."""
        rows = self.conn.execute(
            """SELECT p.*, ps.status FROM players p
               JOIN player_status ps ON ps.player_id = p.id
               WHERE ps.status = 'prospect' AND p.league_id = %s
               ORDER BY p.last_name, p.first_name""",
            (league_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_preferences(self, draft_id: str, gm_id: str) -> list[str]:
        """Return ordered list of player_ids from a GM's draft preferences."""
        rows = self.conn.execute(
            """SELECT dp.player_id FROM draft_preferences dp
               WHERE dp.draft_id = %s AND dp.gm_id = %s
               ORDER BY dp.rank""",
            (draft_id, gm_id),
        ).fetchall()
        return [r["player_id"] for r in rows]

    def get_pick_position(self, draft_id: str, team_id: str) -> int | None:
        """Return the team's pick position from draft_order, or None."""
        try:
            row = self.conn.execute(
                "SELECT pick_position FROM draft_order WHERE draft_id = %s AND team_id = %s",
                (draft_id, team_id),
            ).fetchone()
            return row["pick_position"] if row else None
        except Exception:
            return None  # table doesn't exist on older DBs

    def get_picks_with_details(self, draft_id: str) -> list[dict]:
        """Return all picks for a draft with player and team info, ordered by pick number."""
        rows = self.conn.execute(
            """SELECT dp.round, dp.pick_number, dp.team_id, dp.player_id, dp.auto_picked,
                      p.first_name, p.last_name, p.position,
                      t.city, t.mascot
               FROM draft_picks dp
               JOIN players p ON p.id = dp.player_id
               JOIN teams t ON t.id = dp.team_id
               WHERE dp.draft_id = %s
               ORDER BY dp.pick_number""",
            (draft_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def validate_player_ids(self, player_ids: list[str]) -> str | None:
        """
        Check that all player_ids exist. Returns the first missing id, or None
        if all are valid.
        """
        rows = self.conn.execute(
            "SELECT id FROM players WHERE id = ANY(%s)", (player_ids,)
        ).fetchall()
        found = {r["id"] for r in rows}
        missing = next((pid for pid in player_ids if pid not in found), None)
        return missing

    # ── Write ─────────────────────────────────────────────────────────────────

    def save_preferences(
        self, draft_id: str, gm_id: str, player_ids: list[str]
    ) -> None:
        """Atomically replace a GM's draft preference list."""
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM draft_preferences WHERE gm_id = %s AND draft_id = %s",
                (gm_id, draft_id),
            )
            cur.executemany(
                "INSERT INTO draft_preferences (gm_id, draft_id, player_id, rank) VALUES (%s, %s, %s, %s)",
                [
                    (gm_id, draft_id, pid, rank + 1)
                    for rank, pid in enumerate(player_ids)
                ],
            )
