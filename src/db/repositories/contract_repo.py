# src/db/repositories/contract_repo.py
"""
Player contracts (rules in src/player/contracts.py).

Uses tables:
- player_contracts  one row per deal: salary a season, first season, length
- team_players / player_status  who is on a team, and so needs a deal
- draft_picks / drafts          where a rookie was picked

A contract isn't tied to a team: a traded player keeps his deal, and a team's
payroll is the deals of the players on its roster.

Releases (migration 072): a released deal is no longer his from the season
he's released. A guaranteed one (he's been on the 40-man under it, or he
signed it as a free agent) stays on the releasing team's payroll as dead
money for the seasons it had left. A deal that was never guaranteed costs
nothing to release, and isn't on the payroll in the first place: only
guaranteed money is.
"""

from __future__ import annotations

import random

from src.league import budget as bg
from src.player import contracts as ct
from src.player.player_value import role_rating

# Statuses that play under a contract: everyone a team holds.
SIGNED_STATUSES = ("26man", "40man", "minors")
# Being on the 40-man under a deal guarantees it.
FORTY_MAN_STATUSES = ("26man", "40man")

# A deal still his in a season: not released, or released after it.
IN_FORCE = "(c.released_year IS NULL OR c.released_year > %s)"


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
        "guaranteed": bool(row.get("guaranteed")),
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
            f"""
            SELECT * FROM player_contracts c
            WHERE c.player_id = ANY(%s)
              AND c.start_year <= %s AND c.start_year + c.years > %s
              AND {IN_FORCE}
            ORDER BY c.start_year
            """,
            (ids, year, year, year),
        ).fetchall()
        return {r["player_id"]: dict(r) for r in rows}

    def history(self, player_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM player_contracts WHERE player_id = %s ORDER BY start_year",
            (player_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def payroll(self, team_id: str, year: int) -> int:
        """What the team owes this season: the guaranteed deals of the
        players it holds, plus dead money for players it released."""
        row = self.conn.execute(
            f"""
            SELECT COALESCE(SUM(c.salary), 0) AS total
            FROM team_players tp
            JOIN player_status ps ON ps.player_id = tp.player_id
            JOIN player_contracts c ON c.player_id = tp.player_id
            WHERE tp.team_id = %s AND ps.status = ANY(%s) AND c.guaranteed
              AND c.start_year <= %s AND c.start_year + c.years > %s
              AND {IN_FORCE}
            """,
            (team_id, list(SIGNED_STATUSES), year, year, year),
        ).fetchone()
        return int(row["total"]) + self.dead_money(team_id, year)

    def dead_money(self, team_id: str, year: int) -> int:
        """This season's salary of the guaranteed deals the team released."""
        return sum(r["salary"] for r in self.dead_money_rows(team_id, year))

    def dead_money_rows(self, team_id: str, year: int) -> list[dict]:
        """Each released deal the team still pays this season: the player,
        his salary, and the last season it's owed."""
        rows = self.conn.execute(
            """
            SELECT c.player_id, c.salary, c.start_year + c.years - 1 AS through,
                   p.first_name, p.last_name
            FROM player_contracts c
            JOIN players p ON p.id = c.player_id
            WHERE c.released_team_id = %s AND c.guaranteed
              AND c.released_year <= %s AND c.start_year + c.years > %s
            ORDER BY c.salary DESC
            """,
            (team_id, year, year),
        ).fetchall()
        return [dict(r) for r in rows]

    def guarantee(self, player_ids) -> None:
        """Make the deals of any of these players now on a 40-man
        guaranteed: his newest deal still in force."""
        ids = list(player_ids)
        if not ids:
            return
        self.conn.execute(
            """
            UPDATE player_contracts c SET guaranteed = TRUE
            FROM player_status ps
            WHERE ps.player_id = c.player_id AND c.player_id = ANY(%s)
              AND ps.status = ANY(%s)
              AND NOT c.guaranteed AND c.released_year IS NULL
              AND c.start_year = (SELECT MAX(c2.start_year) FROM player_contracts c2
                                  WHERE c2.player_id = c.player_id
                                    AND c2.released_year IS NULL)
            """,
            (ids, list(FORTY_MAN_STATUSES)),
        )

    def release(self, player_id: str, team_id: str, year: int) -> dict:
        """End his deal from this season. Returns what the team still owes:
        {"salary", "seasons", "total", "through"}, all zero when the deal
        wasn't guaranteed (or he had none)."""
        deal = self.active(player_id, year)
        owed = {"salary": 0, "seasons": 0, "total": 0, "through": None}
        if deal is None:
            return owed
        self.conn.execute(
            """UPDATE player_contracts
               SET released_year = %s, released_team_id = %s
               WHERE id = %s""",
            (year, team_id, deal["id"]),
        )
        if deal["guaranteed"]:
            seasons = _years_left(deal, year)
            owed = {
                "salary": deal["salary"],
                "seasons": seasons,
                "total": deal["salary"] * seasons,
                "through": year + seasons - 1,
            }
        return owed

    def release_cost(self, player_id: str, year: int) -> dict:
        """What releasing him would leave on his team's books, without
        doing it. Same shape as release()."""
        deal = self.active(player_id, year)
        if deal is None or not deal["guaranteed"]:
            return {"salary": 0, "seasons": 0, "total": 0, "through": None}
        seasons = _years_left(deal, year)
        return {
            "salary": deal["salary"],
            "seasons": seasons,
            "total": deal["salary"] * seasons,
            "through": year + seasons - 1,
        }

    def sign_free_agent(
        self, player_id: str, league_id: str, team_id: str, deal: ct.Deal, year: int
    ) -> None:
        """A free agent signing: his deal from this season, guaranteed."""
        self._insert(player_id, league_id, team_id, deal, year, guaranteed=True)

    def last_team(self, player_ids) -> dict[str, str]:
        """The team each player last had a deal with, if any."""
        ids = list(player_ids)
        if not ids:
            return {}
        rows = self.conn.execute(
            """
            SELECT DISTINCT ON (c.player_id) c.player_id,
                   COALESCE(c.released_team_id, c.team_id) AS team_id
            FROM player_contracts c
            WHERE c.player_id = ANY(%s)
            ORDER BY c.player_id, c.start_year DESC, c.id DESC
            """,
            (ids,),
        ).fetchall()
        return {r["player_id"]: r["team_id"] for r in rows if r["team_id"]}

    def _insert(
        self,
        player_id,
        league_id,
        team_id,
        deal: ct.Deal,
        start_year,
        pick=None,
        guaranteed=False,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO player_contracts (
                player_id, league_id, team_id, kind, salary, start_year, years,
                pick_number, guaranteed
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (player_id, start_year) WHERE released_year IS NULL
            DO NOTHING
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
                guaranteed,
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
                    AND (c.released_year IS NULL OR c.released_year > %s)
              )
            ORDER BY tp.team_id, tp.player_id
            """,
            (league_id, teams, list(SIGNED_STATUSES), year, year, year),
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

        # A player re-signing brings his mood to the table
        # (src/player/happiness.py resign_terms).
        from src.db.repositories.happiness_repo import HappinessRepository

        happy = HappinessRepository(self.conn, league_id)
        # New deals are priced in step with the league's payroll cap
        # (src/league/budget.py salary_scale).
        from src.db.repositories.budget_repo import BudgetRepository

        first = BudgetRepository(self.conn).first_year(league_id)

        def scale(at: int) -> float:
            return 1.0 if first is None else bg.salary_scale(at - first)

        happy.prepare_resign([r["player_id"] for r in rows if r["signed_before"]])
        unhappy_out: list[tuple[str, str]] = []

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
                deal = ct.rookie_deal(r["pick_number"], scale(draft_year))
                self._insert(
                    pid, league_id, r["team_id"], deal, draft_year, r["pick_number"]
                )
                signed += 1
                continue

            p = records.get(pid)
            if p is None:
                continue
            kind = "pitcher" if p.is_pitcher() else "hitter"
            deal = ct.standard_deal(p.age, role_rating(p), kind, rng, scale(year))
            start = year
            if not r["signed_before"]:
                start -= ct.years_already_served(deal.years, rng)
            else:
                deal, wants_out = self._mood_terms(
                    happy, pid, r["team_id"], deal, scale(year)
                )
                if wants_out:
                    unhappy_out.append((pid, r["team_id"]))
            self._insert(pid, league_id, r["team_id"], deal, start)
            signed += 1
        happy.request_trades(unhappy_out, year)
        # Those already on a 40-man have guaranteed deals.
        self.guarantee([r["player_id"] for r in rows])
        return signed

    @staticmethod
    def _mood_terms(happy, pid: str, team_id: str, deal: ct.Deal, scale: float = 1.0):
        """His new deal with his mood worked in: a discount when he's happy
        and loyal, more money for fewer years when he isn't."""
        mult, max_years, wants_out = happy.resign_terms(pid)
        years = deal.years if max_years is None else min(deal.years, max_years)
        salary = ct.round_salary(deal.salary * mult, scale)
        return ct.Deal(salary, years, deal.kind), wants_out
