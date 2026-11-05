# src/db/repositories/budget_repo.py
"""
Team budgets and luxury tax (rules in src/league/budget.py).

Uses tables:
- team_budgets  one row per team and season: the budget, and the luxury tax
                once the season is over
- player_contracts (through ContractRepository) for payroll

A league's rows are made the first time they're needed for a season, so a
league needs no setup step and older leagues pick budgets up on their own.
"""

from __future__ import annotations

from src.db.repositories.contract_repo import ContractRepository
from src.league import budget as bg
from src.league.league_modes import get_mode


class BudgetRepository:
    def __init__(self, conn):
        self.conn = conn
        self.contracts = ContractRepository(conn)

    def enabled(self, league_id: str) -> bool:
        row = self.conn.execute(
            "SELECT mode FROM leagues WHERE id = %s", (league_id,)
        ).fetchone()
        return bool(row) and get_mode(row["mode"]).budgets

    def _team_ids(self, league_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT team_id FROM league_season_teams WHERE league_id = %s",
            (league_id,),
        ).fetchall()
        return [r["team_id"] for r in rows]

    def for_league(self, league_id: str, year: int) -> dict[str, int]:
        """{team_id: budget} for the season, making any that are missing.
        Empty when the league has no budgets."""
        if not self.enabled(league_id):
            return {}
        rows = self.conn.execute(
            "SELECT team_id, budget FROM team_budgets"
            " WHERE league_id = %s AND year = %s",
            (league_id, year),
        ).fetchall()
        have = {r["team_id"]: int(r["budget"]) for r in rows}
        missing = [t for t in self._team_ids(league_id) if t not in have]
        if not missing:
            return have
        made = self._make(league_id, year, missing)
        for team_id, amount in made.items():
            self.conn.execute(
                """INSERT INTO team_budgets (league_id, team_id, year, budget)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (league_id, team_id, year) DO NOTHING""",
                (league_id, team_id, year, amount),
            )
        return {**have, **made}

    def _make(self, league_id: str, year: int, team_ids: list[str]) -> dict[str, int]:
        """New budgets: each team's last one grown to this season, or the
        league's first budget for a team that has none yet."""
        last = {
            r["team_id"]: (int(r["budget"]), r["year"])
            for r in self.conn.execute(
                """SELECT DISTINCT ON (team_id) team_id, budget, year
                   FROM team_budgets
                   WHERE league_id = %s AND year < %s
                   ORDER BY team_id, year DESC""",
                (league_id, year),
            ).fetchall()
        }
        first = None
        out = {}
        for team_id in team_ids:
            if team_id in last:
                amount, then = last[team_id]
                out[team_id] = bg.grown(amount, year - then)
                continue
            if first is None:
                first = self._first_budget(league_id, year, last)
            out[team_id] = first
        return out

    def _first_budget(self, league_id: str, year: int, last: dict) -> int:
        """Every team's starting budget. If other teams already have budgets
        (a team new to the league), it gets the newest one grown to now;
        otherwise it's the league's average payroll this season."""
        if last:
            amount, then = max(last.values(), key=lambda v: (v[1], v[0]))
            return bg.grown(amount, year - then)
        payrolls = [self.contracts.payroll(t, year) for t in self._team_ids(league_id)]
        return bg.first_budget(payrolls)

    def budget(self, league_id: str, team_id: str, year: int) -> int | None:
        return self.for_league(league_id, year).get(team_id)

    def standing(self, league_id: str, team_id: str, year: int) -> dict | None:
        """Payroll against budget, for the views; None without budgets."""
        amount = self.budget(league_id, team_id, year)
        if amount is None:
            return None
        return bg.standing(self.contracts.payroll(team_id, year), amount)

    def assess(self, league_id: str, year: int) -> dict[str, int]:
        """The season is over: record each team's luxury tax on its final
        payroll. Returns {team_id: tax}."""
        taxes = {}
        for team_id, amount in self.for_league(league_id, year).items():
            tax = bg.luxury_tax(self.contracts.payroll(team_id, year), amount)
            self.conn.execute(
                """UPDATE team_budgets SET luxury_tax = %s
                   WHERE league_id = %s AND team_id = %s AND year = %s""",
                (tax, league_id, team_id, year),
            )
            taxes[team_id] = tax
        return taxes

    def tax_paid(self, league_id: str, team_id: str) -> list[dict]:
        """Seasons the team paid luxury tax, newest first."""
        rows = self.conn.execute(
            """SELECT year, budget, luxury_tax FROM team_budgets
               WHERE league_id = %s AND team_id = %s AND luxury_tax > 0
               ORDER BY year DESC""",
            (league_id, team_id),
        ).fetchall()
        return [dict(r) for r in rows]
