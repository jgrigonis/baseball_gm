# src/db/repositories/pick_rights_repo.py
#
# Who owns each draft pick: draft_pick_rights has a row for every team's pick
# in every round of a year's draft, with the team that owns it now.


class PickRightsRepository:
    def __init__(self, conn):
        self.conn = conn

    def ensure(self, league_id: str, draft_year: int, team_ids, rounds: int) -> None:
        """Give each team its own picks in a year's draft, where it has none
        yet. Rows already there, traded or not, are left alone."""
        self.conn.cursor().executemany(
            """INSERT INTO draft_pick_rights
                   (league_id, draft_year, round, original_team_id, current_owner_id)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT DO NOTHING""",
            [
                (league_id, draft_year, rnd, t, t)
                for t in team_ids
                for rnd in range(1, rounds + 1)
            ],
        )

    def owners(self, league_id: str, draft_year: int) -> dict[tuple[int, str], str]:
        """{(round, original_team_id): current_owner_id} for a year's draft."""
        rows = self.conn.execute(
            """SELECT round, original_team_id, current_owner_id
               FROM draft_pick_rights WHERE league_id = %s AND draft_year = %s""",
            (league_id, draft_year),
        ).fetchall()
        return {
            (r["round"], r["original_team_id"]): r["current_owner_id"] for r in rows
        }

    def owned_by(
        self, league_id: str, draft_year: int, team_id: str, max_round: int
    ) -> list[dict]:
        """A team's picks in a year's draft up to max_round, by round."""
        rows = self.conn.execute(
            """SELECT round, original_team_id FROM draft_pick_rights
               WHERE league_id = %s AND draft_year = %s
                 AND current_owner_id = %s AND round <= %s
               ORDER BY round, original_team_id""",
            (league_id, draft_year, team_id, max_round),
        ).fetchall()
        return [dict(r) for r in rows]

    def owner(
        self, league_id: str, draft_year: int, rnd: int, original_team_id: str
    ) -> str | None:
        row = self.conn.execute(
            """SELECT current_owner_id FROM draft_pick_rights
               WHERE league_id = %s AND draft_year = %s AND round = %s
                 AND original_team_id = %s""",
            (league_id, draft_year, rnd, original_team_id),
        ).fetchone()
        return row["current_owner_id"] if row else None

    def move(
        self, league_id: str, draft_year: int, rnd: int, original_team_id: str, to: str
    ) -> None:
        self.conn.execute(
            """UPDATE draft_pick_rights SET current_owner_id = %s
               WHERE league_id = %s AND draft_year = %s AND round = %s
                 AND original_team_id = %s""",
            (to, league_id, draft_year, rnd, original_team_id),
        )

    def draft_for_year(self, league_id: str, draft_year: int) -> dict | None:
        """The league's draft for a year, if it's been set up."""
        row = self.conn.execute(
            """SELECT d.* FROM drafts d
               JOIN seasons s ON s.id = d.season_id
               WHERE d.league_id = %s AND s.year = %s""",
            (league_id, draft_year),
        ).fetchone()
        return dict(row) if row else None

    def draft_positions(self, draft_id: str) -> dict[str, int]:
        """{team_id: pick position in round 1} from a draft's order."""
        rows = self.conn.execute(
            "SELECT team_id, pick_position FROM draft_order WHERE draft_id = %s",
            (draft_id,),
        ).fetchall()
        return {r["team_id"]: r["pick_position"] for r in rows}
