# src/db/repositories/budget_repo.py
"""
Team budgets, luxury tax and team money (rules in src/league/budget.py and
src/league/finances.py).

Uses tables:
- team_budgets  one row per team and season: the budget its owner set, the
                revenue and fan interest it was set from, and once the season
                is over the luxury tax, playoff gate, payroll, profit and fan
                interest after
- team_owners, owner_personas  for each owner's Spending
- player_contracts (through ContractRepository) for payroll

A league's rows are made the first time they're needed for a season, so a
league needs no setup step and older leagues pick budgets up on their own.
"""

from __future__ import annotations

from src.db.repositories.contract_repo import ContractRepository
from src.league import budget as bg
from src.league import finances as fn
from src.league import team_pool
from src.league.league_modes import get_mode


class BudgetRepository:
    def __init__(self, conn):
        self.conn = conn
        self.contracts = ContractRepository(conn)
        self._pending: dict[str, tuple[int, int]] = {}

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
        self._pending: dict[str, tuple[int, int]] = {}
        made = self._make(league_id, year, missing)
        for team_id, amount in made.items():
            revenue, fans = self._pending.get(team_id, (None, None))
            self.conn.execute(
                """INSERT INTO team_budgets
                       (league_id, team_id, year, budget, revenue, fans_before)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT (league_id, team_id, year) DO NOTHING""",
                (league_id, team_id, year, amount, revenue, fans),
            )
        return {**have, **made}

    def _make(self, league_id: str, year: int, team_ids: list[str]) -> dict[str, int]:
        """New budgets, set by each team's owner (src/league/finances.py):
        a share of the revenue its market and fans bring in, by how freely
        the owner spends. Scaled so the league's average budget is the flat
        one: the average payroll the first season, then 5% more a season.
        Also records each team's expected revenue and starting fan interest."""
        average = self._average_budget(league_id, year)
        money = self._team_money(league_id, year, team_ids)
        plans = fn.plan(average, money)
        for team_id, p in plans.items():
            self._pending[team_id] = (p.revenue, int(round(money[team_id].fans)))
        return {t: p.budget for t, p in plans.items()}

    def _average_budget(self, league_id: str, year: int) -> int:
        """What the league's average budget is this season: the newest
        season's average grown to now, or the average payroll if there's
        none yet."""
        row = self.conn.execute(
            """SELECT year, AVG(budget) AS avg FROM team_budgets
               WHERE league_id = %s AND year < %s
               GROUP BY year ORDER BY year DESC LIMIT 1""",
            (league_id, year),
        ).fetchone()
        if row:
            return bg.grown(int(row["avg"]), year - row["year"])
        payrolls = [self.contracts.payroll(t, year) for t in self._team_ids(league_id)]
        return bg.first_budget(payrolls)

    def _team_money(
        self, league_id: str, year: int, team_ids: list[str]
    ) -> dict[str, fn.TeamMoney]:
        """Each team's market, fan interest coming into the season, and its
        owner's Spending (the middle when it has no owner yet)."""
        teams = {
            r["id"]: r
            for r in self.conn.execute(
                "SELECT id, city, mascot FROM teams WHERE id = ANY(%s)", (team_ids,)
            ).fetchall()
        }
        spending = {
            r["team_id"]: r["traits"].get("spending", 50)
            for r in self.conn.execute(
                """SELECT t.team_id, o.traits FROM team_owners t
                   JOIN owner_personas o ON o.id = t.owner_id
                   WHERE t.league_id = %s""",
                (league_id,),
            ).fetchall()
        }
        fans = {
            r["team_id"]: r["fans_after"]
            for r in self.conn.execute(
                """SELECT DISTINCT ON (team_id) team_id, fans_after
                   FROM team_budgets
                   WHERE league_id = %s AND year < %s AND fans_after IS NOT NULL
                   ORDER BY team_id, year DESC""",
                (league_id, year),
            ).fetchall()
        }
        out = {}
        for team_id in team_ids:
            t = teams.get(team_id)
            pool = (
                team_pool.get(t["city"], t["mascot"]) or team_pool.by_city(t["city"])
                if t
                else None
            )
            out[team_id] = fn.TeamMoney(
                market=pool.market if pool else 3,
                fans=fans.get(team_id, fn.FAN_START),
                spending=int(spending.get(team_id, 50)),
            )
        return out

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
        payroll, its fans after the season, its playoff gate and its profit
        (src/league/finances.py). Returns {team_id: tax}."""
        budgets = self.for_league(league_id, year)
        if not budgets:
            return {}
        rows = {
            r["team_id"]: r
            for r in self.conn.execute(
                """SELECT team_id, budget, revenue, fans_before FROM team_budgets
                   WHERE league_id = %s AND year = %s""",
                (league_id, year),
            ).fetchall()
        }
        season = self.conn.execute(
            """SELECT s.id FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s AND s.year = %s AND NOT s.is_backstory""",
            (league_id, year),
        ).fetchone()
        results = self._results(league_id, season["id"]) if season else {}
        money = self._team_money(league_id, year, list(budgets))
        # A season budgeted before owners set budgets has no revenue yet:
        # back it out of the budget and the owner's share.
        revenue = {
            t: rows[t]["revenue"]
            or round(budgets[t] / fn.spend_share(money[t].spending))
            for t in budgets
        }
        average = sum(revenue.values()) / len(revenue)
        costs = fn.fixed_costs(average)
        taxes = {}
        for team_id, amount in budgets.items():
            payroll = self.contracts.payroll(team_id, year)
            tax = bg.luxury_tax(payroll, amount)
            r = results.get(team_id, {})
            before = rows[team_id]["fans_before"]
            before = money[team_id].fans if before is None else before
            fans = fn.fans_after(
                before,
                r.get("win_pct", 0.5),
                r.get("playoffs", False),
                r.get("champion", False),
                r.get("all_stars", 0),
            )
            gate = fn.playoff_gate(average, r.get("home_playoff_games", 0))
            total = revenue[team_id] + gate
            self.conn.execute(
                """UPDATE team_budgets
                   SET luxury_tax = %s, revenue = %s, fans_before = %s,
                       fans_after = %s, playoff_revenue = %s, payroll = %s,
                       profit = %s
                   WHERE league_id = %s AND team_id = %s AND year = %s""",
                (
                    tax,
                    revenue[team_id],
                    int(round(before)),
                    fans,
                    gate,
                    payroll,
                    fn.profit(total, payroll, tax, costs),
                    league_id,
                    team_id,
                    year,
                ),
            )
            taxes[team_id] = tax
        return taxes

    def _results(self, league_id: str, season_id: str) -> dict[str, dict]:
        """Each team's season, for fan interest and the playoff gate: win %,
        whether it made the playoffs or won the title, its All-Stars and its
        home playoff games."""
        out: dict[str, dict] = {}
        for r in self.conn.execute(
            """SELECT tgs.team_id, SUM(tgs.win) AS w, SUM(tgs.loss) AS l
               FROM team_game_stats tgs
               JOIN games g ON g.id = tgs.game_id
               WHERE g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
               GROUP BY tgs.team_id""",
            (season_id,),
        ).fetchall():
            games = (r["w"] or 0) + (r["l"] or 0)
            out[r["team_id"]] = {"win_pct": (r["w"] or 0) / games if games else 0.5}
        for r in self.conn.execute(
            """SELECT team_id, COUNT(*) AS n FROM (
                   SELECT home_team_id AS team_id, home_team_id AS host FROM games
                   WHERE season_id = %s AND series_id IS NOT NULL AND completed = 1
                   UNION ALL
                   SELECT away_team_id, home_team_id FROM games
                   WHERE season_id = %s AND series_id IS NOT NULL AND completed = 1
               ) x WHERE team_id = host GROUP BY team_id""",
            (season_id, season_id),
        ).fetchall():
            out.setdefault(r["team_id"], {})["home_playoff_games"] = r["n"]
        for r in self.conn.execute(
            """SELECT DISTINCT team_id FROM (
                   SELECT home_team_id AS team_id FROM games
                   WHERE season_id = %s AND series_id IS NOT NULL
                   UNION SELECT away_team_id FROM games
                   WHERE season_id = %s AND series_id IS NOT NULL) x""",
            (season_id, season_id),
        ).fetchall():
            out.setdefault(r["team_id"], {})["playoffs"] = True
        champ = self.conn.execute(
            """SELECT g.winner_id, COUNT(*) AS n FROM games g
               JOIN series s ON s.id = g.series_id
               WHERE s.season_id = %s AND s.name = 'Finals' AND g.completed = 1
               GROUP BY g.winner_id ORDER BY n DESC LIMIT 1""",
            (season_id,),
        ).fetchone()
        if champ and champ["winner_id"]:
            out.setdefault(champ["winner_id"], {})["champion"] = True
        for r in self.conn.execute(
            """SELECT team_id, COUNT(*) AS n FROM all_stars
               WHERE season_id = %s GROUP BY team_id""",
            (season_id,),
        ).fetchall():
            out.setdefault(r["team_id"], {})["all_stars"] = r["n"]
        return out

    def finances(self, league_id: str, year: int) -> dict[str, dict]:
        """Each team's money for a season, by team id, for the admin pages."""
        rows = self.conn.execute(
            """SELECT team_id, budget, revenue, playoff_revenue, payroll,
                      luxury_tax, profit, fans_before, fans_after
               FROM team_budgets WHERE league_id = %s AND year = %s""",
            (league_id, year),
        ).fetchall()
        return {r["team_id"]: dict(r) for r in rows}

    def tax_paid(self, league_id: str, team_id: str) -> list[dict]:
        """Seasons the team paid luxury tax, newest first."""
        rows = self.conn.execute(
            """SELECT year, budget, luxury_tax FROM team_budgets
               WHERE league_id = %s AND team_id = %s AND luxury_tax > 0
               ORDER BY year DESC""",
            (league_id, team_id),
        ).fetchall()
        return [dict(r) for r in rows]
