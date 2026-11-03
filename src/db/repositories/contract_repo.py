# src/db/repositories/contract_repo.py
"""
Player contracts (rules in src/player/contracts.py).

Uses tables:
- player_contracts  one row per deal: salary a season, first season, length
- team_players / player_status  who is on a team, and so needs a deal
- draft_picks / drafts          where a rookie was picked

A contract isn't tied to a team: a traded player keeps his deal, and a team's
payroll is the deals of the players on its roster.
"""

from __future__ import annotations

import random

from src.player import contracts as ct
from src.player.player_value import role_rating

# Statuses that play under a contract: everyone a team holds.
SIGNED_STATUSES = ("26man", "40man", "minors")


def _years_left(row: dict, year: int) -> int:
    return row["start_year"] + row["years"] - year


def view(row: dict | None, year: int) -> dict | None:
    """A contract for display: salary text, which year of how many, and the
    last season it covers."""
    if row is None:
        return None
    return {
        "kind": row["kind"],
        "salary": row["salary"],
        "salary_text": ct.format_salary(row["salary"]),
        "years": row["years"],
        "year_of": year - row["start_year"] + 1,
        "years_left": _years_left(row, year),
        "through": row["start_year"] + row["years"] - 1,
        "pick_number": row.get("pick_number"),
    }


class ContractRepository:
    def __init__(self, conn):
        self.conn = conn

    def current_year(self, league_id: str) -> int | None:
        """The league's newest season, the one contracts are shown for."""
        row = self.conn.execute(
            """SELECT MAX(s.year) AS year FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s""",
            (league_id,),
        ).fetchone()
        return row["year"] if row else None

    def active(self, player_id: str, year: int) -> dict | None:
        """The deal a player plays under in this season, if any."""
        return self.active_for([player_id], year).get(player_id)

    def active_for(self, player_ids, year: int) -> dict[str, dict]:
        ids = list(player_ids)
        if not ids:
            return {}
        rows = self.conn.execute(
            """
            SELECT * FROM player_contracts
            WHERE player_id = ANY(%s)
              AND start_year <= %s AND start_year + years > %s
            ORDER BY start_year
            """,
            (ids, year, year),
        ).fetchall()
        return {r["player_id"]: dict(r) for r in rows}

    def history(self, player_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM player_contracts WHERE player_id = %s ORDER BY start_year",
            (player_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def payroll(self, team_id: str, year: int) -> int:
        """What the team pays this season: the deals of everyone it holds."""
        row = self.conn.execute(
            """
            SELECT COALESCE(SUM(c.salary), 0) AS total
            FROM team_players tp
            JOIN player_status ps ON ps.player_id = tp.player_id
            JOIN player_contracts c ON c.player_id = tp.player_id
            WHERE tp.team_id = %s AND ps.status = ANY(%s)
              AND c.start_year <= %s AND c.start_year + c.years > %s
            """,
            (team_id, list(SIGNED_STATUSES), year, year),
        ).fetchone()
        return int(row["total"])

    def _insert(
        self, player_id, league_id, team_id, deal: ct.Deal, start_year, pick=None
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO player_contracts (
                player_id, league_id, team_id, kind, salary, start_year, years,
                pick_number
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (player_id, start_year) DO NOTHING
            """,
            (
                player_id,
                league_id,
                team_id,
                deal.kind,
                deal.salary,
                start_year,
                deal.years,
                pick,
            ),
        )

    def sign_unsigned(self, league_id: str, year: int) -> int:
        """
        Give a deal to everyone on one of the league's teams who has none
        for this season. Returns how many signed.

        - Drafted in this league and never signed: his rookie deal, from the
          season he was drafted for (if it hasn't already run out).
        - Never signed otherwise (a starting roster): a standard deal he's
          already partway through.
        - His last deal ran out: a new standard deal from this season.
        """
        teams = [
            r["team_id"]
            for r in self.conn.execute(
                "SELECT DISTINCT team_id FROM league_season_teams WHERE league_id = %s",
                (league_id,),
            ).fetchall()
        ]
        if not teams:
            return 0
        rows = self.conn.execute(
            """
            SELECT tp.team_id, tp.player_id,
                   EXISTS (SELECT 1 FROM player_contracts c
                           WHERE c.player_id = tp.player_id) AS signed_before,
                   pick.pick_number, pick.year AS draft_year
            FROM team_players tp
            JOIN player_status ps ON ps.player_id = tp.player_id
            LEFT JOIN LATERAL (
                SELECT dp.pick_number, s.year
                FROM draft_picks dp
                JOIN drafts d ON d.id = dp.draft_id
                JOIN seasons s ON s.id = d.season_id
                WHERE dp.player_id = tp.player_id AND d.league_id = %s
                ORDER BY s.year DESC LIMIT 1
            ) pick ON TRUE
            WHERE tp.team_id = ANY(%s) AND ps.status = ANY(%s)
              AND NOT EXISTS (
                  SELECT 1 FROM player_contracts c
                  WHERE c.player_id = tp.player_id
                    AND c.start_year <= %s AND c.start_year + c.years > %s
              )
            ORDER BY tp.team_id, tp.player_id
            """,
            (league_id, teams, list(SIGNED_STATUSES), year, year),
        ).fetchall()
        if not rows:
            return 0

        # Imported here: player_repo -> team_repo -> ... imports repositories.
        from src.db.repositories.player_repo import PlayerRepository

        player_repo = PlayerRepository(self.conn)
        records: dict[str, object] = {}
        for team_id in {r["team_id"] for r in rows}:
            for p in player_repo.get_players_by_team(team_id):
                records[p.id] = p

        signed = 0
        for r in rows:
            pid = r["player_id"]
            rng = random.Random(f"contract:{pid}:{year}")
            draft_year = r["draft_year"]
            if (
                not r["signed_before"]
                and draft_year is not None
                and draft_year <= year < draft_year + ct.ROOKIE_YEARS
            ):
                deal = ct.rookie_deal(r["pick_number"])
                self._insert(
                    pid, league_id, r["team_id"], deal, draft_year, r["pick_number"]
                )
                signed += 1
                continue

            p = records.get(pid)
            if p is None:
                continue
            kind = "pitcher" if p.is_pitcher() else "hitter"
            deal = ct.standard_deal(p.age, role_rating(p), kind, rng)
            start = year
            if not r["signed_before"]:
                start -= ct.years_already_served(deal.years, rng)
            self._insert(pid, league_id, r["team_id"], deal, start)
            signed += 1
        return signed
