# src/db/repositories/budget_repo.py
"""
Team budgets, luxury tax and team money (rules in src/league/budget.py and
src/league/finances.py).

Uses tables:
- team_budgets  one row per team and season: the league's payroll cap (the
                same in every row of a season), the budget its owner set
                from it, the revenue and fan interest coming in, and once the season
                is over the luxury tax, playoff gate, payroll, profit and fan
                interest after
- team_owners, owner_personas  for each owner's Spending
- player_contracts (through ContractRepository) for payroll, and how many
                what its never-guaranteed minor leaguers are paid (not
                payroll, but it counts against the owner's budget)

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
            return self._with_farm(league_id, year, have)
        self._pending: dict[str, tuple[int, int]] = {}
        cap = self.cap(league_id, year)
        made = self._make(league_id, year, missing, cap)
        ai = self._ai_teams(league_id)
        spending = self._spending(league_id)
        for team_id, amount in made.items():
            revenue, fans = self._pending.get(team_id, (None, None))
            # AI GMs fund their front office by their owner (src/league/
            # budget.py ai_levels); a person's starts at Standard.
            levels = (
                bg.ai_levels(spending.get(team_id, 50), f"fo:{team_id}:{year}")
                if team_id in ai
                else {}
            )
            self.conn.execute(
                """INSERT INTO team_budgets
                       (league_id, team_id, year, cap, budget, revenue, fans_before,
                        coaching, facilities, analytics)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (league_id, team_id, year) DO NOTHING""",
                (
                    league_id, team_id, year, cap, amount, revenue, fans,
                    levels.get("coaching"), levels.get("facilities"),
                    levels.get("analytics"),
                ),
            )  # fmt: skip
        return self._with_farm(league_id, year, {**have, **made})

    def _with_farm(
        self, league_id: str, year: int, budgets: dict[str, int]
    ) -> dict[str, int]:
        """The stored budgets plus each owner's farm allowance, worked out
        live from the league's minor league salaries now, so the draft or a
        release moves it (src/league/budget.py farm_allowance)."""
        allowances = self.farm_allowances(league_id, year)
        return {t: b + allowances.get(t, 0) for t, b in budgets.items()}

    def farm_allowances(self, league_id: str, year: int) -> dict[str, int]:
        """What each owner adds to their budget for the minor leagues, by
        team id: the league's average farm times their share by Spending."""
        average = bg.average_farm(self._minor_leagues(league_id, year).values())
        spending = self._spending(league_id)
        return {
            t: bg.farm_allowance(average, spending.get(t, 50))
            for t in self._team_ids(league_id)
        }

    def _ai_teams(self, league_id: str) -> set[str]:
        return {
            r["team_id"]
            for r in self.conn.execute(
                "SELECT team_id FROM gms WHERE league_id = %s AND is_ai",
                (league_id,),
            ).fetchall()
        }

    # ── The front office ─────────────────────────────────────────────────────

    def levels(self, league_id: str, team_id: str, year: int) -> dict[str, int]:
        """The team's front office levels for the season (Standard where
        unset). Empty without budgets."""
        if self.budget(league_id, team_id, year) is None:
            return {}
        row = self.conn.execute(
            """SELECT coaching, facilities, analytics FROM team_budgets
               WHERE league_id = %s AND team_id = %s AND year = %s""",
            (league_id, team_id, year),
        ).fetchone()
        return {
            k: bg.STANDARD if row is None or row[k] is None else bg.clean_level(row[k])
            for k in bg.DEPARTMENT_KEYS
        }

    def league_levels(self, league_id: str, year: int) -> dict[str, dict[str, int]]:
        """Every team's front office levels for the season, by team id."""
        if not self.for_league(league_id, year):
            return {}
        rows = self.conn.execute(
            """SELECT team_id, coaching, facilities, analytics FROM team_budgets
               WHERE league_id = %s AND year = %s""",
            (league_id, year),
        ).fetchall()
        return {
            r["team_id"]: {
                k: bg.STANDARD if r[k] is None else bg.clean_level(r[k])
                for k in bg.DEPARTMENT_KEYS
            }
            for r in rows
        }

    def department(
        self, league_id: str, year: int, department: str, team_ids
    ) -> dict[str, int]:
        """One department's level for these teams this season, by team id,
        Standard where unset or without budgets. A plain read for the game
        loop: it makes no rows."""
        if department not in bg.DEPARTMENT_KEYS:
            raise ValueError(department)
        ids = list(team_ids)
        out = dict.fromkeys(ids, bg.STANDARD)
        if not ids:
            return out
        for r in self.conn.execute(
            f"""SELECT team_id, {department} AS level FROM team_budgets
                WHERE league_id = %s AND year = %s AND team_id = ANY(%s)""",
            (league_id, year, ids),
        ).fetchall():
            if r["level"] is not None:
                out[r["team_id"]] = bg.clean_level(r["level"])
        return out

    def front_office(self, league_id: str, team_id: str, year: int) -> int:
        """What the team's front office costs this season (0 without
        budgets)."""
        levels = self.levels(league_id, team_id, year)
        if not levels:
            return 0
        return bg.front_office_cost(self.cap(league_id, year), levels)

    def _minor_leagues(
        self, league_id: str, year: int, team_ids=None
    ) -> dict[str, int]:
        """What each team pays its minor leaguers off the payroll this
        season, by team id. Every team in the league unless team_ids says
        which."""
        ids = self._team_ids(league_id) if team_ids is None else list(team_ids)
        return self.contracts.minor_league_pay(ids, year)

    def minor_leagues(self, league_id: str, team_id: str, year: int) -> int:
        """What the team's farm costs this season (0 without budgets)."""
        if not self.enabled(league_id):
            return 0
        return self._minor_leagues(league_id, year, [team_id])[team_id]

    def league_minor_leagues(self, league_id: str, year: int) -> dict[str, int]:
        """Every team's farm cost this season, by team id; empty without
        budgets."""
        if not self.enabled(league_id):
            return {}
        return self._minor_leagues(league_id, year)

    def set_level(
        self, league_id: str, team_id: str, year: int, department: str, level: int
    ) -> None:
        """Set one department's level (the caller checks it's allowed)."""
        if department not in bg.DEPARTMENT_KEYS:
            raise ValueError(department)
        self.for_league(league_id, year)
        self.conn.execute(
            f"""UPDATE team_budgets SET {department} = %s
                WHERE league_id = %s AND team_id = %s AND year = %s""",
            (bg.clean_level(level), league_id, team_id, year),
        )

    # ── Ticket prices ────────────────────────────────────────────────────────

    def ticket_price(self, league_id: str, team_id: str, year: int) -> int | None:
        """The team's ticket price level for the season (1 to 10), or None
        without budgets."""
        if self.budget(league_id, team_id, year) is None:
            return None
        row = self.conn.execute(
            """SELECT ticket_price FROM team_budgets
               WHERE league_id = %s AND team_id = %s AND year = %s""",
            (league_id, team_id, year),
        ).fetchone()
        return fn.ticket_level(row["ticket_price"] if row else None)

    def set_ticket_price(
        self, league_id: str, team_id: str, year: int, level: int
    ) -> None:
        """Set the team's ticket prices (the caller checks it's allowed)."""
        self.for_league(league_id, year)
        self.conn.execute(
            """UPDATE team_budgets SET ticket_price = %s
               WHERE league_id = %s AND team_id = %s AND year = %s""",
            (fn.ticket_level(level), league_id, team_id, year),
        )

    def _make(
        self, league_id: str, year: int, team_ids: list[str], cap: int
    ) -> dict[str, int]:
        """New budgets, set by each team's owner from the league's cap, by
        how freely they spend (src/league/budget.py). Also records each
        team's expected revenue and starting fan interest
        (src/league/finances.py)."""
        money = self._team_money(league_id, year, team_ids)
        plans = fn.plan(cap, money)
        for team_id, p in plans.items():
            self._pending[team_id] = (p.revenue, int(round(money[team_id].fans)))
        # The farm allowance is added live (_with_farm), not stored.
        return {t: p.budget for t, p in plans.items()}

    def cap(self, league_id: str, year: int) -> int:
        """The league's payroll cap for the season, the same for every
        team: the one already set, else the newest season's grown to now,
        else the league's average payroll."""
        row = self.conn.execute(
            """SELECT year, MAX(cap) AS cap FROM team_budgets
               WHERE league_id = %s AND year <= %s AND cap IS NOT NULL
               GROUP BY year ORDER BY year DESC LIMIT 1""",
            (league_id, year),
        ).fetchone()
        if row:
            return bg.grown(int(row["cap"]), year - row["year"])
        payrolls = [self.contracts.payroll(t, year) for t in self._team_ids(league_id)]
        return bg.first_cap(payrolls)

    def first_year(self, league_id: str) -> int | None:
        """The league's first season with a cap; None without budgets."""
        if not self.enabled(league_id):
            return None
        row = self.conn.execute(
            "SELECT MIN(year) AS y FROM team_budgets"
            " WHERE league_id = %s AND cap IS NOT NULL",
            (league_id,),
        ).fetchone()
        return row["y"] if row and row["y"] is not None else None

    def salary_scale(self, league_id: str, year: int) -> float:
        """How far contract prices have grown with the cap by this season
        (src/league/budget.py salary_scale). 1 before the league's first
        cap, and always 1 without budgets (Speed Blitz)."""
        first = self.first_year(league_id)
        return 1.0 if first is None else bg.salary_scale(year - first)

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
        spending = self._spending(league_id)
        banks = self.banks(league_id, year)
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
                bank_change=banks[team_id]["change"] if team_id in banks else 0,
            )
        return out

    def _spending(self, league_id: str) -> dict[str, int]:
        """Each owned team's owner's Spending trait."""
        return {
            r["team_id"]: int(r["traits"].get("spending", 50))
            for r in self.conn.execute(
                """SELECT t.team_id, o.traits FROM team_owners t
                   JOIN owner_personas o ON o.id = t.owner_id
                   WHERE t.league_id = %s""",
                (league_id,),
            ).fetchall()
        }

    # ── The owner's bank ─────────────────────────────────────────────────────

    def _open_banks(self, league_id: str, year: int) -> None:
        """Give any owner without a bank their starting one, from this
        season's cap (src/league/budget.py starting_bank)."""
        rows = self.conn.execute(
            """SELECT team_id FROM team_owners
               WHERE league_id = %s AND bank_start IS NULL""",
            (league_id,),
        ).fetchall()
        if not rows:
            return
        spending = self._spending(league_id)
        cap = self.cap(league_id, year)
        for r in rows:
            start = bg.starting_bank(cap, spending.get(r["team_id"], 50))
            self.conn.execute(
                """UPDATE team_owners SET bank_start = %s, bank_year = %s
                   WHERE league_id = %s AND team_id = %s AND bank_start IS NULL""",
                (start, year, league_id, r["team_id"]),
            )

    def banks(self, league_id: str, year: int | None = None) -> dict[str, dict]:
        """Each owner's bank by team id: where it started, and its balance
        coming into this season (every season's profit before it), or with
        year None, now (every season taxed so far). Opens any missing ones
        from the season's cap. Empty without budgets."""
        if not self.enabled(league_id):
            return {}
        if year is not None:
            self._open_banks(league_id, year)
        rows = self.conn.execute(
            """SELECT t.team_id, t.bank_start, t.bank_year,
                      COALESCE(SUM(b.profit) FILTER (
                          WHERE b.year >= t.bank_year
                            AND (%s::INT IS NULL OR b.year < %s::INT)), 0) AS made
               FROM team_owners t
               LEFT JOIN team_budgets b
                 ON b.league_id = t.league_id AND b.team_id = t.team_id
               WHERE t.league_id = %s AND t.bank_start IS NOT NULL
               GROUP BY t.team_id, t.bank_start, t.bank_year""",
            (year, year, league_id),
        ).fetchall()
        return {
            r["team_id"]: {
                "start": int(r["bank_start"]),
                "since": r["bank_year"],
                "balance": int(r["bank_start"]) + int(r["made"]),
                "change": int(r["made"]),
            }
            for r in rows
        }

    def budget(self, league_id: str, team_id: str, year: int) -> int | None:
        return self.for_league(league_id, year).get(team_id)

    def standing(self, league_id: str, team_id: str, year: int) -> dict | None:
        """Payroll against the cap, the owner's budget and their hard limit,
        for the views; None without budgets."""
        amount = self.budget(league_id, team_id, year)
        if amount is None:
            return None
        cap = self.cap(league_id, year)
        bank = self.banks(league_id).get(team_id)
        limit = bg.hard_limit(cap, amount, bank["balance"] if bank else None)
        return bg.standing(
            self.contracts.payroll(team_id, year),
            cap,
            amount,
            limit,
            bg.front_office_cost(cap, self.levels(league_id, team_id, year)),
            self.minor_leagues(league_id, team_id, year),
            self.farm_allowances(league_id, year).get(team_id, 0),
        )

    def refusal(
        self, league_id: str, team_id: str, year: int, added: int
    ) -> str | None:
        """Why the owner refuses a move that adds this much payroll (past
        their hard limit), or None. Always None without budgets."""
        if added <= 0:
            return None
        standing = self.standing(league_id, team_id, year)
        if standing is None:
            return None
        return bg.refusal(standing["spend"], standing["limit"], added)

    def history(self, league_id: str, team_id: str) -> list[dict]:
        """The team's money season by season, newest first, for the Budget
        tab, with the owner's bank after each finished season."""
        rows = [
            dict(r)
            for r in self.conn.execute(
                """SELECT year, cap, budget, payroll, revenue, playoff_revenue,
                          luxury_tax, tax_share, front_office, minor_league,
                          profit,
                          fans_before, fans_after, ticket_price
                   FROM team_budgets WHERE league_id = %s AND team_id = %s
                   ORDER BY year""",
                (league_id, team_id),
            ).fetchall()
        ]
        bank = self.banks(league_id).get(team_id)
        balance = None
        if bank:
            balance = bank["start"]
        for r in rows:
            if bank and r["year"] >= bank["since"] and r["profit"] is not None:
                balance += r["profit"]
                r["bank_after"] = balance
            else:
                r["bank_after"] = None
        return list(reversed(rows))

    def assess(self, league_id: str, year: int) -> dict[str, int]:
        """The season is over: record each team's luxury tax on its final
        payroll over the league's cap, its fans after the season, its playoff gate and its profit
        (src/league/finances.py). Returns {team_id: tax}."""
        budgets = self.for_league(league_id, year)
        if not budgets:
            return {}
        rows = {
            r["team_id"]: r
            for r in self.conn.execute(
                """SELECT team_id, budget, revenue, fans_before, ticket_price
                   FROM team_budgets WHERE league_id = %s AND year = %s""",
                (league_id, year),
            ).fetchall()
        }
        season_id = self._season_id(league_id, year)
        results = self._results(league_id, season_id) if season_id else {}
        cap = self.cap(league_id, year)
        money = self._team_money(league_id, year, list(budgets))
        revenue = self._revenues(league_id, year, rows, money, cap)
        average = sum(revenue.values()) / len(revenue)
        # A Standard front office and an average farm are in every owner's
        # budget, so the fixed costs leave them out; each team pays for its
        # own front office and minor leaguers. A full farm can be bigger than
        # the fixed costs, so this can go below zero: the league's money
        # covering an average farm.
        farms = self._minor_leagues(league_id, year, list(budgets))
        costs = self._fixed_costs(average, cap) - bg.average_farm(farms.values())
        levels = self.league_levels(league_id, year)
        payrolls = {t: self.contracts.payroll(t, year) for t in budgets}
        shares = bg.tax_shares(payrolls, cap)
        taxes = {}
        for team_id in budgets:
            payroll = payrolls[team_id]
            tax = bg.luxury_tax(payroll, cap)
            share = shares.get(team_id, 0)
            office = bg.front_office_cost(cap, levels.get(team_id, {}))
            farm = farms.get(team_id, 0)
            r = results.get(team_id, {})
            before = rows[team_id]["fans_before"]
            before = money[team_id].fans if before is None else before
            fans = fn.fans_after(
                before,
                r.get("win_pct", 0.5),
                r.get("playoffs", False),
                r.get("champion", False),
                r.get("all_stars", 0),
                rows[team_id]["ticket_price"],
            )
            gate = fn.playoff_gate(average, r.get("home_playoff_games", 0))
            tickets = fn.ticket_revenue(revenue[team_id], rows[team_id]["ticket_price"])
            total = tickets + gate
            self.conn.execute(
                """UPDATE team_budgets
                   SET luxury_tax = %s, revenue = %s, fans_before = %s,
                       fans_after = %s, playoff_revenue = %s, payroll = %s,
                       tax_share = %s, front_office = %s, minor_league = %s,
                       profit = %s
                   WHERE league_id = %s AND team_id = %s AND year = %s""",
                (
                    tax,
                    revenue[team_id],
                    int(round(before)),
                    fans,
                    gate,
                    payroll,
                    share,
                    office,
                    farm,
                    fn.profit(total, payroll, tax, costs, share, office, farm),
                    league_id,
                    team_id,
                    year,
                ),
            )
            taxes[team_id] = tax
        return taxes

    def _season_id(self, league_id: str, year: int) -> str | None:
        row = self.conn.execute(
            """SELECT s.id FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s AND s.year = %s AND NOT s.is_backstory""",
            (league_id, year),
        ).fetchone()
        return row["id"] if row else None

    def _revenues(
        self, league_id: str, year: int, rows: dict, money: dict, cap: int
    ) -> dict[str, int]:
        """Each team's revenue for the season (before the playoff gate). A
        season budgeted before owners set budgets has none stored yet, so
        it's planned now."""
        if all(r["revenue"] is not None for r in rows.values()):
            return {t: int(r["revenue"]) for t, r in rows.items()}
        planned = fn.plan(cap, money)
        return {t: int(rows[t]["revenue"] or planned[t].revenue) for t in rows}

    @staticmethod
    def _fixed_costs(average_revenue: float, cap: int) -> int:
        """The season's fixed costs, the same for every team. A Standard
        front office is in every owner's budget, so they leave it out; each
        team pays for its own front office."""
        return fn.fixed_costs(average_revenue) - bg.standard_front_office(cap)

    def books(self, league_id: str, team_id: str, year: int) -> list[dict]:
        """The team's money in and out season by season, newest first, for
        the Budget tab's revenue breakdown (src/league/finances.py books).
        This season, until its books close, is projected: today's payroll,
        tax and tax share, and the playoff gate so far. Empty without
        budgets."""
        if self.budget(league_id, team_id, year) is None:
            return []
        rows = self.conn.execute(
            """SELECT team_id, year, cap, revenue, playoff_revenue, payroll,
                      luxury_tax, tax_share, front_office, minor_league, profit,
                      fans_before, ticket_price
               FROM team_budgets WHERE league_id = %s AND year <= %s""",
            (league_id, year),
        ).fetchall()
        seasons: dict[int, dict] = {}
        for r in rows:
            seasons.setdefault(r["year"], {})[r["team_id"]] = r
        market = self._team_money(league_id, year, [team_id])[team_id].market
        out = []
        for y in sorted(seasons, reverse=True):
            league_rows = seasons[y]
            mine = league_rows.get(team_id)
            if mine is None:
                continue
            done = mine["profit"] is not None
            if not done and y != year:
                continue
            cap = int(mine["cap"]) if mine["cap"] else self.cap(league_id, y)
            money = self._team_money(league_id, y, list(league_rows))
            revenue = self._revenues(league_id, y, league_rows, money, cap)
            average = sum(revenue.values()) / len(revenue)
            per_game = fn.playoff_gate(average, 1)
            fans = mine["fans_before"]
            fans = money[team_id].fans if fans is None else fans
            if done:
                gate = int(mine["playoff_revenue"] or 0)
                line = dict(
                    playoff_gate=gate,
                    home_playoff_games=round(gate / per_game) if per_game else 0,
                    tax_share=int(mine["tax_share"] or 0),
                    payroll=int(mine["payroll"] or 0),
                    front_office=int(mine["front_office"] or 0),
                    luxury_tax=int(mine["luxury_tax"] or 0),
                    minor_league=int(mine["minor_league"] or 0),
                    # Seasons closed before the farm counted have no
                    # minor_league stored, and no farm help either.
                    farm_help=bg.average_farm(
                        int(r["minor_league"])
                        for r in league_rows.values()
                        if r["minor_league"] is not None
                    ),
                    profit=int(mine["profit"]),
                )
            else:
                season_id = self._season_id(league_id, y)
                games = (
                    self._results(league_id, season_id)
                    .get(team_id, {})
                    .get("home_playoff_games", 0)
                    if season_id
                    else 0
                )
                payrolls = {t: self.contracts.payroll(t, y) for t in league_rows}
                farms = self._minor_leagues(league_id, y, list(league_rows))
                line = dict(
                    minor_league=farms.get(team_id, 0),
                    farm_help=bg.average_farm(farms.values()),
                    playoff_gate=fn.playoff_gate(average, games),
                    home_playoff_games=games,
                    tax_share=bg.tax_shares(payrolls, cap).get(team_id, 0),
                    payroll=payrolls[team_id],
                    front_office=self.front_office(league_id, team_id, y),
                    luxury_tax=bg.luxury_tax(payrolls[team_id], cap),
                )
            out.append(
                {
                    "year": y,
                    **fn.books(
                        revenue=revenue[team_id],
                        market=market,
                        fans=fans,
                        gate_per_game=per_game,
                        costs=self._fixed_costs(average, cap),
                        ticket_price=mine["ticket_price"],
                        **line,
                    ),
                }
            )
        return out

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
            """SELECT team_id, cap, budget, revenue, playoff_revenue, payroll,
                      luxury_tax, tax_share, profit, fans_before, fans_after
               FROM team_budgets WHERE league_id = %s AND year = %s""",
            (league_id, year),
        ).fetchall()
        return {r["team_id"]: dict(r) for r in rows}

    def league_payrolls(self, league_id: str, year: int) -> list[dict]:
        """Every team's payroll, luxury tax and tax share season by season,
        newest first, for the Budget tab's league table. Each season is
        {"year", "cap", "projected", "teams": {team_id: {payroll, tax,
        share}}}. This season, until its books close, is projected from
        today's payrolls; finished seasons are as recorded. Empty without
        budgets."""
        if not self.for_league(league_id, year):
            return []
        rows = self.conn.execute(
            """SELECT team_id, year, cap, payroll, luxury_tax, tax_share, profit
               FROM team_budgets WHERE league_id = %s AND year <= %s""",
            (league_id, year),
        ).fetchall()
        seasons: dict[int, dict] = {}
        for r in rows:
            seasons.setdefault(r["year"], {})[r["team_id"]] = r
        out = []
        for y in sorted(seasons, reverse=True):
            league_rows = seasons[y]
            done = all(r["profit"] is not None for r in league_rows.values())
            if not done and y != year:
                continue
            cap = next(
                (int(r["cap"]) for r in league_rows.values() if r["cap"]), None
            ) or self.cap(league_id, y)
            if done:
                teams = {
                    t: {
                        "payroll": int(r["payroll"] or 0),
                        "tax": int(r["luxury_tax"] or 0),
                        "share": int(r["tax_share"] or 0),
                    }
                    for t, r in league_rows.items()
                }
            else:
                payrolls = {t: self.contracts.payroll(t, y) for t in league_rows}
                shares = bg.tax_shares(payrolls, cap)
                teams = {
                    t: {
                        "payroll": p,
                        "tax": bg.luxury_tax(p, cap),
                        "share": shares.get(t, 0),
                    }
                    for t, p in payrolls.items()
                }
            out.append({"year": y, "cap": cap, "projected": not done, "teams": teams})
        return out

    def tax_paid(self, league_id: str, team_id: str) -> list[dict]:
        """Seasons the team paid luxury tax, newest first."""
        rows = self.conn.execute(
            """SELECT year, budget, luxury_tax FROM team_budgets
               WHERE league_id = %s AND team_id = %s AND luxury_tax > 0
               ORDER BY year DESC""",
            (league_id, team_id),
        ).fetchall()
        return [dict(r) for r in rows]
