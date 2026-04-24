# src/db/repositories/draft_repo.py
import uuid


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

    def get_ids_and_rank_from_preferences(
        self, draft_id: str, league_id: str
    ) -> list[dict]:
        pref_rows = self.conn.execute(
            """
            SELECT g.team_id, dp.player_id, dp.rank
            FROM draft_preferences dp
            JOIN gms g ON g.id = dp.gm_id
            WHERE dp.draft_id = %s
            AND g.league_id = %s
            AND NOT g.is_ai
            AND g.team_id IS NOT NULL
            ORDER BY g.team_id, dp.rank
            """,
            (draft_id, league_id),
        ).fetchall()
        return pref_rows

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

    def get_draft_id(self, league_id: str, season_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT id FROM drafts WHERE league_id = %s AND season_id = %s",
            (league_id, season_id),
        ).fetchone()
        if row:
            return row["id"]

    def get_draft(self, draft_id: str) -> dict | None:
        draft = self.conn.execute(
            "SELECT id, league_id, season_id, format, state FROM drafts WHERE id = %s",
            (draft_id,),
        ).fetchone()
        if draft:
            return dict(draft)

    def get_team_id_draft_order(self, draft_id: str) -> list[str]:
        order = self.conn.execute(
            """SELECT team_id FROM draft_order WHERE draft_id = %s ORDER BY pick_position""",
            (draft_id,),
        ).fetchall()
        return order

    def get_all_teams_city_mascot(self, season_id: str) -> list[dict]:
        all_team_rows = self.conn.execute(
            """
            SELECT DISTINCT lst.team_id, t.city, t.mascot
            FROM league_season_teams lst
            JOIN teams t ON lst.team_id = t.id
            WHERE lst.season_id = %s
            """,
            (season_id,),
        ).fetchall()
        return all_team_rows

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

    def create_draft(self, league_id: str, season_id: str, draft_format: str) -> str:
        draft_id = str(uuid.uuid4())
        self.conn.execute(
            "INSERT INTO drafts (id, league_id, season_id, format, state) VALUES (%s, %s, %s, %s, 'pending')",
            (draft_id, league_id, season_id, draft_format),
        )
        return draft_id

    def set_draft_state(self, draft_id: str, state: str) -> None:
        self.conn.execute(
            "UPDATE drafts SET state = %s WHERE id = %s",
            (
                state,
                draft_id,
            ),
        )

    def set_complete_current_pick(self, draft_id: str, current_pick: int) -> None:
        self.conn.execute(
            "UPDATE drafts SET state = 'complete', current_pick = %s WHERE id = %s",
            (
                current_pick,
                draft_id,
            ),
        )

    def insert_draft_picks(
        self,
        draft_id: str,
        pick_number: int,
        pick_round: int,
        gm_id: str,
        team_id: str,
        player_id: str,
        auto_pick: bool,
        picked_at: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO draft_picks
                (draft_id, pick_number, round, gm_id, team_id, player_id, auto_picked, picked_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                draft_id,
                pick_number,
                pick_round,
                gm_id,
                team_id,
                player_id,
                auto_pick,
                picked_at,
            ),
        )

    def clear_draft(self, draft_id: str, league_id: str, draft_year: int) -> None:
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM draft_order WHERE draft_id = %s", (draft_id,))
            cur.execute(
                "DELETE FROM draft_pick_rights WHERE league_id = %s AND draft_year = %s",
                (league_id, draft_year),
            )

    def insert_draft_order(self, draft_id: str, team_id: str, position: int) -> None:
        self.conn.execute(
            "INSERT INTO draft_order (draft_id, team_id, pick_position) VALUES (%s, %s, %s)",
            (draft_id, team_id, position),
        )

    def insert_draft_pick_rights(
        self,
        league_id: str,
        draft_year: int,
        round: int,
        og_team_id: str,
        cur_team_id: str,
    ) -> None:
        self.conn.execute(
            """INSERT INTO draft_pick_rights
                (league_id, draft_year, round, original_team_id, current_owner_id)
                VALUES (%s, %s, %s, %s, %s)""",
            (league_id, draft_year, round, og_team_id, cur_team_id),
        )
