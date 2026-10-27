# src/db/repositories/draft_repo.py
import uuid

from psycopg.types.json import Jsonb

from src.league.offseason.draft_strategy import DraftStrategy
from src.player.player_record import PlayerRecord
from src.player.player_skills import PlayerSkills


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

    def get_prospect_records(self, league_id: str) -> list[PlayerRecord]:
        """Every prospect in the league's pool with skills, in one query, in
        the same name order the draft loads them."""
        rows = self.conn.execute(
            """SELECT p.id, p.first_name, p.last_name, p.bats, p.throws,
                      p.position, sk.*
               FROM players p
               JOIN player_status ps ON ps.player_id = p.id
               JOIN player_skills sk ON sk.player_id = p.id
               WHERE ps.status = 'prospect' AND p.league_id = %s
               ORDER BY p.last_name, p.first_name""",
            (league_id,),
        ).fetchall()
        return [_record(r) for r in rows]

    def get_roster_records(
        self, team_ids: list[str]
    ) -> dict[str, list[tuple[PlayerRecord, str]]]:
        """{team_id: [(player, status)]} for every player the teams own, in
        one query."""
        rows = self.conn.execute(
            """SELECT tp.team_id, ps.status, p.id, p.first_name, p.last_name,
                      p.bats, p.throws, p.position, sk.*
               FROM team_players tp
               JOIN players p ON p.id = tp.player_id
               JOIN player_status ps ON ps.player_id = p.id
               JOIN player_skills sk ON sk.player_id = p.id
               WHERE tp.team_id = ANY(%s)
               ORDER BY tp.team_id, p.last_name, p.first_name""",
            (team_ids,),
        ).fetchall()
        rosters: dict[str, list[tuple[PlayerRecord, str]]] = {t: [] for t in team_ids}
        for r in rows:
            rosters[r["team_id"]].append((_record(r), r["status"]))
        return rosters

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

    def get_strategy(self, draft_id: str, gm_id: str) -> DraftStrategy | None:
        """Return a GM's saved draft strategy, or None."""
        row = self.conn.execute(
            """SELECT chips, age_pref, pins FROM draft_strategies
               WHERE draft_id = %s AND gm_id = %s""",
            (draft_id, gm_id),
        ).fetchone()
        return _strategy(row) if row else None

    def get_strategies_by_team(
        self, draft_id: str, league_id: str
    ) -> dict[str, DraftStrategy]:
        """{team_id: DraftStrategy} for the league's human GMs who saved one."""
        rows = self.conn.execute(
            """
            SELECT g.team_id, ds.chips, ds.age_pref, ds.pins
            FROM draft_strategies ds
            JOIN gms g ON g.id = ds.gm_id
            WHERE ds.draft_id = %s
            AND g.league_id = %s
            AND NOT g.is_ai
            AND g.team_id IS NOT NULL
            """,
            (draft_id, league_id),
        ).fetchall()
        return {r["team_id"]: _strategy(r) for r in rows}

    def get_pick_position(self, draft_id: str, team_id: str) -> int | None:
        """Return the team's pick position from draft_order, or None."""
        cursor = self.conn.cursor()
        row = cursor.execute(
            "SELECT pick_position FROM draft_order WHERE draft_id = %s AND team_id = %s",
            (draft_id, team_id),
        ).fetchone()
        return row["pick_position"] if row else None

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

    def get_for_season(self, league_id: str, season_id: str) -> dict | None:
        """Return the draft held before this season, or None."""
        row = self.conn.execute(
            "SELECT * FROM drafts WHERE league_id = %s AND season_id = %s",
            (league_id, season_id),
        ).fetchone()
        return dict(row) if row else None

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

    def clear_preferences(self, draft_id: str, gm_id: str) -> None:
        """Drop a GM's hand-ordered preference list."""
        self.conn.execute(
            "DELETE FROM draft_preferences WHERE gm_id = %s AND draft_id = %s",
            (gm_id, draft_id),
        )

    def save_strategy(self, draft_id: str, gm_id: str, strategy: DraftStrategy) -> None:
        """Insert or replace a GM's draft strategy."""
        self.conn.execute(
            """INSERT INTO draft_strategies (gm_id, draft_id, chips, age_pref, pins)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (gm_id, draft_id) DO UPDATE
               SET chips = EXCLUDED.chips, age_pref = EXCLUDED.age_pref,
                   pins = EXCLUDED.pins, updated_at = NOW()""",
            (
                gm_id,
                draft_id,
                Jsonb(strategy.chips),
                strategy.age_pref,
                strategy.pins,
            ),
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


def _strategy(row) -> DraftStrategy:
    return DraftStrategy(
        chips=dict(row["chips"]), age_pref=row["age_pref"], pins=list(row["pins"])
    )


def _record(row) -> PlayerRecord:
    return PlayerRecord(
        id=row["id"],
        first_name=row["first_name"],
        last_name=row["last_name"],
        bats=row["bats"],
        throws=row["throws"],
        position=row["position"],
        skills=PlayerSkills.from_db_row(row),
    )
