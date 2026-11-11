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
- broadcast_deals  each team's local TV deals (price locked when signed)
- ballpark_projects  each team's ballpark upgrades, paid from the owner's bank
- team_owners, owner_personas  for each owner's Spending
- player_season_stats, all_stars, season_awards, player_status  for who
                sells jerseys for each team (merchandise)
- player_contracts (through ContractRepository) for payroll, and how many
                what its never-guaranteed minor leaguers are paid (not
                payroll, but it counts against the owner's budget)

A league's rows are made the first time they're needed for a season, so a
league needs no setup step and older leagues pick budgets up on their own.
"""

from __future__ import annotations

import random

from src.db.repositories.contract_repo import ContractRepository
from src.league import budget as bg
from src.league import finances as fn
from src.league import team_pool
from src.league.league_modes import get_mode
from src.player import contracts as ct
from src.player.contracts import format_salary


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
        self._rich_custom_owners(league_id, year, cap, made)
        ai = self._ai_teams(league_id)
        spending = self._spending(league_id)
        carried = self._prior_settings(
            league_id, year, [t for t in made if t not in ai]
        )
        newcomers = self._new_gm_teams(league_id, year)
        for team_id, amount in made.items():
            revenue, fans = self._pending.get(team_id, (None, None))
            # AI GMs fund their front office by their owner (src/league/
            # budget.py ai_levels); a person's keeps last season's levels
            # (Josh, 2026-11-09), Standard in their first season. A carried
            # level past the owner's limit stays: the Budget tab shows it
            # and Standard is always allowed. Ticket prices carry over the
            # same way.
            levels = (
                bg.ai_levels(spending.get(team_id, 50), f"fo:{team_id}:{year}")
                if team_id in ai
                else carried.get(team_id, {})
            )
            if team_id in newcomers:
                # A GM new to the team starts the front office at Standard,
                # not at what the GMs before them picked (Josh, 2026-11-11).
                levels = {
                    k: v for k, v in levels.items() if k not in bg.DEPARTMENT_KEYS
                }
            self.conn.execute(
                """INSERT INTO team_budgets
                       (league_id, team_id, year, cap, budget, revenue, fans_before,
                        coaching, facilities, analytics, marketing, ticket_price)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (league_id, team_id, year) DO NOTHING""",
                (
                    league_id, team_id, year, cap, amount, revenue, fans,
                    levels.get("coaching"), levels.get("facilities"),
                    levels.get("analytics"), levels.get("marketing"),
                    levels.get("ticket_price"),
                ),
            )  # fmt: skip
        self._ai_ballparks(league_id, year, [t for t in made if t in ai], cap)
        return self._with_farm(league_id, year, {**have, **made})

    def _prior_settings(
        self, league_id: str, year: int, team_ids: list[str]
    ) -> dict[str, dict[str, int]]:
        """Each team's front office levels and ticket price from its latest
        season before this one, by team id; teams without one are left
        out."""
        if not team_ids:
            return {}
        rows = self.conn.execute(
            """SELECT DISTINCT ON (team_id)
                      team_id, coaching, facilities, analytics, marketing,
                      ticket_price
               FROM team_budgets
               WHERE league_id = %s AND year < %s AND team_id = ANY(%s)
               ORDER BY team_id, year DESC""",
            (league_id, year, list(team_ids)),
        ).fetchall()
        return {
            r["team_id"]: {
                k: r[k]
                for k in (*bg.DEPARTMENT_KEYS, "ticket_price")
                if r[k] is not None
            }
            for r in rows
        }

    def _new_gm_teams(self, league_id: str, year: int) -> set[str]:
        """Teams whose person GM took over for this season (gms.joined_year),
        so last season's front office was someone else's."""
        return {
            r["team_id"]
            for r in self.conn.execute(
                """SELECT team_id FROM gms
                   WHERE league_id = %s AND NOT is_ai AND joined_year >= %s""",
                (league_id, year),
            ).fetchall()
        }

    def reset_levels(
        self, league_id: str, team_id: str, from_year: int, *, ai: bool = False
    ) -> None:
        """Give the team's front office fresh levels for its seasons from
        from_year on, when it changes GMs: Standard for a person, the owner's
        usual levels (ai_levels) for an AI GM. Ticket prices stay; they're
        the team's, not the GM's."""
        spending = self._spending(league_id).get(team_id, 50) if ai else None
        for r in self.conn.execute(
            """SELECT year FROM team_budgets
               WHERE league_id = %s AND team_id = %s AND year >= %s""",
            (league_id, team_id, from_year),
        ).fetchall():
            levels = bg.ai_levels(spending, f"fo:{team_id}:{r['year']}") if ai else {}
            self.conn.execute(
                """UPDATE team_budgets
                   SET coaching = %s, facilities = %s, analytics = %s, marketing = %s
                   WHERE league_id = %s AND team_id = %s AND year = %s""",
                (
                    levels.get("coaching"), levels.get("facilities"),
                    levels.get("analytics"), levels.get("marketing"),
                    league_id, team_id, r["year"],
                ),
            )  # fmt: skip

    def custom_team_ids(self, league_id: str) -> set[str]:
        """The league's teams that play with a custom team's players
        (services/league_custom_teams.py)."""
        return {
            r["id"]
            for r in self.conn.execute(
                """SELECT DISTINCT t.id FROM league_custom_teams c
                   JOIN league_season_teams lst ON lst.league_id = c.league_id
                   JOIN teams t ON t.id = lst.team_id
                        AND t.city = c.city AND t.mascot = c.mascot
                   WHERE c.league_id = %s""",
                (league_id,),
            ).fetchall()
        }

    def _rich_custom_owners(
        self, league_id: str, year: int, cap: int, made: dict[str, int]
    ) -> None:
        """A custom team's owner is rich enough for the team brought in
        (Josh, 2026-11-09): their budget covers at least that payroll, as it
        was the first season, plus a standard front office, grown with the
        league's prices since."""
        custom = self.custom_team_ids(league_id) & set(made)
        if not custom:
            return
        first = self.first_year(league_id)
        for team_id in custom:
            if first is None or first >= year:
                base = self.contracts.payroll(team_id, year)
                floor = base + bg.standard_front_office(cap)
            else:
                row = self.conn.execute(
                    """SELECT budget FROM team_budgets
                       WHERE league_id = %s AND team_id = %s AND year = %s""",
                    (league_id, team_id, first),
                ).fetchone()
                if not row:
                    continue
                floor = round(int(row["budget"]) * bg.salary_scale(year - first))
            made[team_id] = max(made[team_id], floor)

    def _with_farm(
        self, league_id: str, year: int, budgets: dict[str, int]
    ) -> dict[str, int]:
        """The stored budgets plus each owner's farm allowance, worked out
        live from the league's minor league salaries now, so the draft or a
        release moves it (src/league/budget.py farm_allowance), and their
        allowance for luxury tax (tax_allowance), worked out live so running
        leagues get it too."""
        allowances = self.farm_allowances(league_id, year)
        cap = self.cap(league_id, year)
        return {
            t: b + allowances.get(t, 0) + bg.tax_allowance(cap, b)
            for t, b in budgets.items()
        }

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
            """SELECT coaching, facilities, analytics, marketing FROM team_budgets
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
            """SELECT team_id, coaching, facilities, analytics, marketing FROM team_budgets
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
        each = ct.minors_salary(self.salary_scale(league_id, year))
        return self.contracts.minor_league_pay(ids, year, each)

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

    def budget_seen(self, league_id: str, team_id: str, year: int) -> bool:
        """Whether the GM has opened the Budget tab between seasons this
        year, while the front office and ticket prices could still change.
        True without budgets (nothing to set)."""
        row = self.conn.execute(
            """SELECT budget_seen FROM team_budgets
               WHERE league_id = %s AND team_id = %s AND year = %s""",
            (league_id, team_id, year),
        ).fetchone()
        if row is None:
            return not self.enabled(league_id)
        return bool(row["budget_seen"])

    def mark_budget_seen(self, league_id: str, team_id: str, year: int) -> None:
        self.conn.execute(
            """UPDATE team_budgets SET budget_seen = TRUE
               WHERE league_id = %s AND team_id = %s AND year = %s
                 AND budget_seen IS NOT TRUE""",
            (league_id, team_id, year),
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
        team: the one already set; else, once the newest season with a cap
        is finished, the average payroll teams have already committed to
        this season (src/league/budget.py next_cap), or that cap grown when
        it isn't finished; else the league's average payroll
        (first_cap)."""
        row = self.conn.execute(
            """SELECT year, MAX(cap) AS cap FROM team_budgets
               WHERE league_id = %s AND year <= %s AND cap IS NOT NULL
               GROUP BY year ORDER BY year DESC LIMIT 1""",
            (league_id, year),
        ).fetchone()
        if row:
            cap, gap = int(row["cap"]), year - row["year"]
            if gap <= 0:
                return cap
            finished = self.conn.execute(
                """SELECT 1 FROM team_budgets
                   WHERE league_id = %s AND year = %s
                     AND payroll IS NOT NULL AND profit IS NOT NULL
                   LIMIT 1""",
                (league_id, row["year"]),
            ).fetchone()
            if not finished:
                return bg.grown(cap, gap)
            # Josh, 2026-11-09: a cap set off last season's final payrolls
            # ran a season late (season 2 left most teams far under it,
            # later seasons nearly all over). It follows what teams owe
            # this season instead, after the re-sign window.
            committed = [
                self.contracts.payroll(t, year) for t in self._team_ids(league_id)
            ]
            return bg.next_cap(bg.grown(cap, gap - 1), committed)
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
                fans=fans[team_id]
                if team_id in fans
                else self._backstory_fans(league_id).get(team_id, fn.FAN_START),
                spending=int(spending.get(team_id, 50)),
                bank_change=banks[team_id]["change"] if team_id in banks else 0,
            )
        return out

    def _backstory_fans(self, league_id: str) -> dict[str, int]:
        """Each team's fan interest coming out of the league's backstory
        (Josh, 2026-11-07): from FAN_START, every past season moves it the
        way a real one would (src/league/finances.py fans_after), so a team
        with a winning past starts with keener fans. Empty without a
        backstory. Seeds a team's first budgeted season only."""
        cache = self.__dict__.setdefault("_backstory_cache", {})
        if league_id in cache:
            return cache[league_id]
        seasons = self.conn.execute(
            """SELECT s.id FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s AND s.is_backstory ORDER BY s.year""",
            (league_id,),
        ).fetchall()
        fans: dict[str, int] = {}
        for season in seasons:
            for team_id, r in self._results(league_id, season["id"]).items():
                if "win_pct" not in r:
                    continue
                fans[team_id] = fn.fans_after(
                    fans.get(team_id, fn.FAN_START),
                    r["win_pct"],
                    r.get("playoffs", False),
                    r.get("champion", False),
                    r.get("all_stars", 0),
                )
        cache[league_id] = fans
        return fans

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
        custom = self.custom_team_ids(league_id)
        for r in rows:
            start = bg.starting_bank(cap, spending.get(r["team_id"], 50))
            if r["team_id"] in custom:
                # A rich owner for a custom team: a season of its payroll more.
                start += self.contracts.payroll(r["team_id"], year)
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
        # Ballpark payments come out between seasons, before the season
        # they're made in, so they're out of the bank coming into it; a new
        # stadium's later ones haven't been paid yet.
        if year is None:
            row = self.conn.execute(
                "SELECT MAX(year) AS y FROM team_budgets WHERE league_id = %s",
                (league_id,),
            ).fetchone()
            upto = row["y"] if row else None
        else:
            upto = year
        payments = self.ballpark_payments(league_id)
        out = {}
        for r in rows:
            spent = sum(
                amount
                for y, amount in payments.get(r["team_id"], [])
                if upto is None or y <= upto
            )
            owed = sum(amount for _, amount in payments.get(r["team_id"], [])) - spent
            out[r["team_id"]] = {
                "start": int(r["bank_start"]),
                "since": r["bank_year"],
                "balance": int(r["bank_start"]) + int(r["made"]) - spent,
                "change": int(r["made"]) - spent,
                "spent": spent,
                # Still to pay on a new stadium going up.
                "owed": owed,
            }
        return out

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
        self,
        league_id: str,
        team_id: str,
        year: int,
        added: int,
        payroll: bool = True,
    ) -> str | None:
        """Why the owner refuses a move that adds this much payroll (or, with
        payroll False, front office money) past their hard limit, or None.
        Added payroll brings its luxury tax with it. Always None without
        budgets."""
        if added <= 0:
            return None
        standing = self.standing(league_id, team_id, year)
        if standing is None:
            return None
        if payroll:
            added = bg.added_cost(standing["payroll"], standing["cap"], added)
        return bg.refusal(standing["spend"], standing["limit"], added)

    def history(self, league_id: str, team_id: str) -> list[dict]:
        """The team's money season by season, newest first, for the Budget
        tab, with the owner's bank after each finished season."""
        rows = [
            dict(r)
            for r in self.conn.execute(
                """SELECT year, cap, budget, payroll, revenue, playoff_revenue,
                          popularity_revenue, broadcast_revenue, merch_revenue,
                          sponsor_revenue, ballpark_revenue, luxury_tax, tax_share, front_office, minor_league,
                          profit,
                          fans_before, fans_after, ticket_price, attendance,
                          crowd_games, capacity, sellouts
                   FROM team_budgets WHERE league_id = %s AND team_id = %s
                   ORDER BY year""",
                (league_id, team_id),
            ).fetchall()
        ]
        bank = self.banks(league_id).get(team_id)
        spent: dict[int, int] = {}
        for y, amount in self.ballpark_payments(league_id).get(team_id, []):
            spent[y] = spent.get(y, 0) + amount
        balance = None
        if bank:
            balance = bank["start"]
        for r in rows:
            r["bank_before"] = r["bank_spent"] = r["bank_after"] = None
            if not bank or r["year"] < bank["since"]:
                continue
            # The season's ballpark payments come out of the bank too; this
            # season's are already out while its profit is still to come.
            r["bank_before"] = balance
            r["bank_spent"] = spent.get(r["year"], 0)
            if r["profit"] is not None:
                balance += r["profit"] - r["bank_spent"]
                r["bank_after"] = balance
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
        deals = self.broadcast_deals(league_id, year)
        merch = self.merchandise(league_id, year)
        sponsors = self.sponsors(league_id, year)
        parks = self.ballparks(league_id, year)
        crowds = self.crowds(league_id, year)
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
                levels.get(team_id, {}).get("marketing"),
                fn.ballpark_fans(parks.get(team_id, ())),
            )
            gate = fn.playoff_gate(average, r.get("home_playoff_games", 0))
            tickets = fn.ticket_revenue(revenue[team_id], rows[team_id]["ticket_price"])
            popular = fn.popularity_money(average, before)
            broadcast = deals[team_id]["amount"] if team_id in deals else 0
            sold = merch[team_id]["total"] if team_id in merch else 0
            sponsor = sponsors[team_id]["total"] if team_id in sponsors else 0
            park = fn.ballpark_money(
                parks.get(team_id, ()),
                average,
                money[team_id].market,
                before,
                revenue[team_id],
                rows[team_id]["ticket_price"],
            )
            seen = crowds.get(team_id)
            crowd = self._crowd_money(seen, tickets)
            total = tickets + crowd + gate + popular + broadcast + sold + sponsor + park
            self.conn.execute(
                """UPDATE team_budgets
                   SET luxury_tax = %s, revenue = %s, fans_before = %s,
                       fans_after = %s, playoff_revenue = %s,
                       popularity_revenue = %s, broadcast_revenue = %s,
                       merch_revenue = %s, sponsor_revenue = %s,
                       sponsor_deal = %s, ballpark_revenue = %s, payroll = %s,
                       tax_share = %s, front_office = %s, minor_league = %s,
                       profit = %s, attendance = %s, crowd_games = %s,
                       crowd_expected = %s, crowd_in_park = %s, capacity = %s,
                       sellouts = %s, crowd_revenue = %s
                   WHERE league_id = %s AND team_id = %s AND year = %s""",
                (
                    tax,
                    revenue[team_id],
                    int(round(before)),
                    fans,
                    gate,
                    popular,
                    broadcast,
                    sold,
                    sponsor,
                    sponsors[team_id]["kind"] if team_id in sponsors else None,
                    park,
                    payroll,
                    share,
                    office,
                    farm,
                    fn.profit(total, payroll, tax, costs, share, office, farm),
                    seen["attendance"] if seen else None,
                    seen["counted"] if seen else None,
                    seen["expected"] if seen else None,
                    seen["in_park"] if seen else None,
                    seen["capacity"] if seen else fn.capacity(parks.get(team_id, ())),
                    seen["sellouts"] if seen else None,
                    crowd,
                    league_id,
                    team_id,
                    year,
                ),
            )
            taxes[team_id] = tax
        return taxes

    # ── Attendance ───────────────────────────────────────────────────────────

    def _markets(self, team_ids) -> dict[str, int]:
        out = {}
        for t in self.conn.execute(
            "SELECT id, city, mascot FROM teams WHERE id = ANY(%s)", (list(team_ids),)
        ).fetchall():
            pool = team_pool.get(t["city"], t["mascot"]) or team_pool.by_city(t["city"])
            out[t["id"]] = pool.market if pool else 3
        return out

    def game_crowd(
        self,
        league_id: str,
        season_id: str,
        game_id: str,
        home_id: str,
        away_id: str,
        day,
        playoffs: bool = False,
    ) -> int | None:
        """Work out and record one game's crowd (src/league/finances.py
        crowd). None in a league without budgets."""
        if not league_id or not self.enabled(league_id):
            return None
        row = self.conn.execute(
            "SELECT year FROM seasons WHERE id = %s", (season_id,)
        ).fetchone()
        if not row:
            return None
        year = row["year"]
        rows = {
            r["team_id"]: r
            for r in self.conn.execute(
                """SELECT team_id, fans_before, ticket_price FROM team_budgets
                   WHERE league_id = %s AND year = %s""",
                (league_id, year),
            ).fetchall()
        }
        home = rows.get(home_id)
        if home is None or home["fans_before"] is None:
            return None
        known = [
            r["fans_before"] for r in rows.values() if r["fans_before"] is not None
        ]
        league_fans = sum(known) / len(known)
        away = rows.get(away_id)
        away_fans = (
            away["fans_before"]
            if away and away["fans_before"] is not None
            else league_fans
        )
        market = self._markets([home_id]).get(home_id, 3)
        seats = fn.capacity(self.ballparks(league_id, year).get(home_id, ()))
        expected = fn.expected_crowd(
            home["fans_before"], market, home["ticket_price"], day
        )
        # Only games before this one's date count: the record so far, and
        # whether it's the home opener.
        when = str(day)
        record = self.conn.execute(
            """SELECT COALESCE(SUM(tgs.win), 0) AS w, COALESCE(SUM(tgs.loss), 0) AS l
               FROM team_game_stats tgs JOIN games g ON g.id = tgs.game_id
               WHERE g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
                 AND tgs.team_id = %s AND g.game_date < %s""",
            (season_id, home_id, when),
        ).fetchone()
        opener = (
            not playoffs
            and not self.conn.execute(
                """SELECT 1 FROM games WHERE season_id = %s AND home_team_id = %s
                     AND series_id IS NULL AND game_date < %s LIMIT 1""",
                (season_id, home_id, when),
            ).fetchone()
        )
        rng = random.Random(f"crowd:{game_id}")
        attendance = fn.crowd(
            expected,
            seats,
            opponent=fn.opponent_mult(away_fans, league_fans),
            form=fn.form_mult(int(record["w"]), int(record["l"])),
            noise=rng.uniform(-1, 1),
            opener=opener,
            playoffs=playoffs,
        )
        self.conn.execute(
            "UPDATE games SET attendance = %s, crowd_expected = %s WHERE id = %s",
            (attendance, int(round(expected)), game_id),
        )
        return attendance

    def crowds(self, league_id: str, year: int, team_ids=None) -> dict[str, dict]:
        """Each team's regular season home crowds so far, by team id:
        home games scheduled (games) and played with a crowd (counted), the
        total crowd and what was expected (uncapped and in its park), seats,
        sellouts, the best crowd, average and share of seats filled. Teams
        with no crowds yet still get their seats and games."""
        season_id = self._season_id(league_id, year)
        if not season_id:
            return {}
        parks = self.ballparks(league_id, year)
        out: dict[str, dict] = {}
        for r in self.conn.execute(
            """SELECT home_team_id AS team_id, COUNT(*) AS games,
                      COUNT(attendance) AS counted,
                      COALESCE(SUM(attendance), 0) AS attendance,
                      COALESCE(SUM(crowd_expected) FILTER
                          (WHERE attendance IS NOT NULL), 0) AS expected,
                      MAX(attendance) AS best,
                      ARRAY_AGG(attendance) FILTER (WHERE attendance IS NOT NULL) AS crowds,
                      ARRAY_AGG(crowd_expected) FILTER (WHERE attendance IS NOT NULL) AS expect
               FROM games
               WHERE season_id = %s AND series_id IS NULL
                 AND (%s::TEXT[] IS NULL OR home_team_id = ANY(%s::TEXT[]))
               GROUP BY home_team_id""",
            (season_id, team_ids, team_ids),
        ).fetchall():
            seats = fn.capacity(parks.get(r["team_id"], ()))
            counted = int(r["counted"])
            total = int(r["attendance"])
            out[r["team_id"]] = {
                "games": int(r["games"]),
                "counted": counted,
                "attendance": total,
                "expected": int(r["expected"]),
                "in_park": sum(min(seats, e or 0) for e in (r["expect"] or [])),
                "capacity": seats,
                "sellouts": sum(1 for c in (r["crowds"] or []) if c >= seats),
                "best": int(r["best"]) if r["best"] is not None else None,
                "average": round(total / counted) if counted else None,
                "full": total / (counted * seats) if counted and seats else None,
            }
        return out

    @staticmethod
    def _crowd_money(crowds: dict | None, tickets: int) -> int:
        if not crowds:
            return 0
        return fn.crowd_money(
            tickets,
            crowds["attendance"],
            crowds["expected"],
            crowds["counted"],
            crowds["games"],
        )

    # ── Broadcast deals ──────────────────────────────────────────────────────

    def _average_revenue(self, league_id: str, year: int) -> float:
        """The league's average regular season revenue this season (before
        ticket prices and the playoff gate)."""
        rows = {
            r["team_id"]: r
            for r in self.conn.execute(
                "SELECT team_id, revenue FROM team_budgets"
                " WHERE league_id = %s AND year = %s",
                (league_id, year),
            ).fetchall()
        }
        if not rows:
            return 0.0
        money = self._team_money(league_id, year, list(rows))
        revenue = self._revenues(
            league_id, year, rows, money, self.cap(league_id, year)
        )
        return sum(revenue.values()) / len(revenue)

    def _past_seasons(self, league_id: str, year: int, count: int) -> list[str]:
        """The ids of the league's seasons (backstory ones too) in the
        count years before this one."""
        return [
            r["id"]
            for r in self.conn.execute(
                """SELECT s.id FROM seasons s
                   JOIN league_seasons ls ON ls.season_id = s.id
                   WHERE ls.league_id = %s AND s.year < %s AND s.year >= %s""",
                (league_id, year, year - count),
            ).fetchall()
        ]

    def _recent_win_pct(
        self, league_id: str, year: int, team_ids: list[str]
    ) -> dict[str, float]:
        """Each team's average win % over the seasons before this one (.500
        when it has none)."""
        seen: dict[str, list[float]] = {}
        for season_id in self._past_seasons(league_id, year, fn.BROADCAST_SEASONS):
            for team_id, r in self._results(league_id, season_id).items():
                if "win_pct" in r:
                    seen.setdefault(team_id, []).append(r["win_pct"])
        return {
            t: sum(seen[t]) / len(seen[t]) if seen.get(t) else 0.5 for t in team_ids
        }

    def broadcast_deals(self, league_id: str, year: int) -> dict[str, dict]:
        """Each team's broadcast deal running this season, by team id,
        signing a new one (at the default length) for any team whose deal
        has run out: priced from its market, fan interest coming into the
        season and recent win % (src/league/finances.py broadcast_base).
        Empty without budgets."""
        if not self.for_league(league_id, year):
            return {}
        teams = self._team_ids(league_id)
        have = {
            r["team_id"]: dict(r)
            for r in self.conn.execute(
                """SELECT DISTINCT ON (team_id) team_id, start_year, years, base,
                          fans, win_pct
                   FROM broadcast_deals
                   WHERE league_id = %s AND start_year <= %s
                   ORDER BY team_id, start_year DESC""",
                (league_id, year),
            ).fetchall()
            if r["start_year"] + r["years"] > year
        }
        missing = [t for t in teams if t not in have]
        if missing:
            average = self._average_revenue(league_id, year)
            money = self._team_money(league_id, year, missing)
            wins = self._recent_win_pct(league_id, year, missing)
            for t in missing:
                fans = int(round(money[t].fans))
                deal = {
                    "team_id": t,
                    "start_year": year,
                    "years": fn.BROADCAST_DEFAULT_YEARS,
                    "base": fn.broadcast_base(average, money[t].market, fans, wins[t]),
                    "fans": fans,
                    "win_pct": round(wins[t], 3),
                }
                self.conn.execute(
                    """INSERT INTO broadcast_deals
                           (league_id, team_id, start_year, years, base, fans, win_pct)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (league_id, team_id, start_year) DO NOTHING""",
                    (
                        league_id, t, year, deal["years"], deal["base"],
                        deal["fans"], deal["win_pct"],
                    ),
                )  # fmt: skip
                have[t] = deal
        return {t: self._deal(d, year) for t, d in have.items()}

    @staticmethod
    def _deal(d: dict, year: int) -> dict:
        years = int(d["years"])
        return {
            "start_year": d["start_year"],
            "years": years,
            "base": int(d["base"]),
            "amount": fn.broadcast_amount(int(d["base"]), years),
            "fans": int(d["fans"]),
            "win_pct": float(d["win_pct"]),
            # Seasons it still pays, this one included.
            "left": d["start_year"] + years - year,
            # Signed this season: its length can still be picked.
            "new": d["start_year"] == year,
        }

    def broadcast_deal(self, league_id: str, team_id: str, year: int) -> dict | None:
        return self.broadcast_deals(league_id, year).get(team_id)

    def deal_in(self, league_id: str, team_id: str, year: int) -> dict | None:
        """The deal that paid the team in a season (no new one signed)."""
        row = self.conn.execute(
            """SELECT start_year, years, base, fans, win_pct FROM broadcast_deals
               WHERE league_id = %s AND team_id = %s AND start_year <= %s
               ORDER BY start_year DESC LIMIT 1""",
            (league_id, team_id, year),
        ).fetchone()
        if not row or row["start_year"] + row["years"] <= year:
            return None
        return self._deal(dict(row), year)

    def set_broadcast_years(
        self, league_id: str, team_id: str, year: int, years: int
    ) -> bool:
        """Pick the length of the deal the team signs this season (the
        caller checks it's allowed). False when its deal wasn't signed this
        season."""
        deal = self.broadcast_deal(league_id, team_id, year)
        if not deal or not deal["new"]:
            return False
        self.conn.execute(
            """UPDATE broadcast_deals SET years = %s
               WHERE league_id = %s AND team_id = %s AND start_year = %s""",
            (fn.broadcast_years(years), league_id, team_id, year),
        )
        return True

    # ── The ballpark ─────────────────────────────────────────────────────────

    def ballpark(self, league_id: str, team_id: str) -> list[dict]:
        """The team's ballpark projects, oldest first: {"project", "year"
        it opens, "ordered", "cost"}."""
        return [
            {
                "project": r["project"],
                "year": r["year"],
                "ordered": r["ordered"],
                "cost": int(r["cost"]),
                "generation": int(r["generation"]),
            }
            for r in self.conn.execute(
                """SELECT project, year, COALESCE(ordered, year) AS ordered, cost,
                          generation
                   FROM ballpark_projects
                   WHERE league_id = %s AND team_id = %s ORDER BY year, project""",
                (league_id, team_id),
            ).fetchall()
        ]

    def ballpark_payments(self, league_id: str) -> dict[str, list[tuple[int, int]]]:
        """Every payment owners make for their ballpark projects, by team
        id: (season, amount), a new stadium's spread over its build."""
        out: dict[str, list[tuple[int, int]]] = {}
        for r in self.conn.execute(
            """SELECT team_id, year, COALESCE(ordered, year) AS ordered, cost
               FROM ballpark_projects WHERE league_id = %s""",
            (league_id,),
        ).fetchall():
            out.setdefault(r["team_id"], []).extend(
                fn.installments(int(r["cost"]), r["ordered"], r["year"])
            )
        return out

    def ballparks(self, league_id: str, year: int | None) -> dict[str, list[str]]:
        """Each team's ballpark projects open this season (with year None,
        all of them), by team id. Only the newest open stadium counts: a
        replacement does away with the old one, and its key carries which
        stadium it is (finances.built_key)."""
        out: dict[str, list[str]] = {}
        stadium: dict[str, tuple] = {}
        for r in self.conn.execute(
            """SELECT team_id, project, year, generation FROM ballpark_projects
               WHERE league_id = %s AND (%s::INT IS NULL OR year <= %s::INT)
               ORDER BY year, generation""",
            (league_id, year, year),
        ).fetchall():
            key = fn.built_key(r["project"], int(r["generation"]))
            if r["project"] in fn.STADIUM_TIERS:
                stadium[r["team_id"]] = key  # the newest wins
                continue
            out.setdefault(r["team_id"], []).append(key)
        for t, key in stadium.items():
            out.setdefault(t, []).append(key)
        return out

    def fans_now(self, league_id: str, team_id: str, year: int) -> int | None:
        """The team's fan interest coming into this season (0 to 100), for
        the Budget tab's Ticket prices card. None without budgets."""
        row = self.conn.execute(
            """SELECT fans_before FROM team_budgets
               WHERE league_id = %s AND team_id = %s AND year = %s""",
            (league_id, team_id, year),
        ).fetchone()
        if row is None:
            return None
        if row["fans_before"] is not None:
            return int(row["fans_before"])
        return int(round(self._team_money(league_id, year, [team_id])[team_id].fans))

    def ballpark_offers(self, league_id: str, team_id: str, year: int) -> list[dict]:
        """Every ballpark project for the team this season, for the Budget
        tab: what it costs, what it would earn a season, its payback, and
        whether it's built, or what the owner still needs to pay for it.
        Empty without budgets."""
        if self.budget(league_id, team_id, year) is None:
            return []
        cap = self.cap(league_id, year)
        row = self.conn.execute(
            """SELECT revenue, fans_before, ticket_price FROM team_budgets
               WHERE league_id = %s AND team_id = %s AND year = %s""",
            (league_id, team_id, year),
        ).fetchone()
        money = self._team_money(league_id, year, [team_id])[team_id]
        fans = money.fans if row["fans_before"] is None else row["fans_before"]
        average = self._average_revenue(league_id, year)
        revenue = int(row["revenue"] or average)
        rows = self.ballpark(league_id, team_id)
        built = {p["project"]: p for p in rows}  # the newest of each
        this_season = sum(1 for p in rows if p["ordered"] == year)
        bank = self.banks(league_id).get(team_id)
        balance = bank["balance"] - bank["owed"] if bank else None
        stadiums = [p for p in rows if p["project"] in fn.STADIUM_TIERS]
        current = stadiums[-1] if stadiums else None
        # A stadium 25 seasons old can be replaced by one of its tier or
        # higher; while one is going up, nothing else.
        replace_from = current["year"] + fn.STADIUM_LIFE if current else None
        can_replace = bool(current) and year >= replace_from
        tier_now = fn.STADIUM_TIERS.index(current["project"]) if current else -1
        out = []
        for p in fn.BALLPARK:
            is_stadium = p.key in fn.STADIUM_TIERS
            mine = built.get(p.key)
            if is_stadium and current and mine is not current:
                mine = None  # an old stadium, replaced
            rebuild = (
                is_stadium and can_replace and fn.STADIUM_TIERS.index(p.key) >= tier_now
            )
            generation = len(stadiums) + 1 if is_stadium else 1
            key = fn.built_key(p.key, generation)
            cost = (
                int(mine["cost"])
                if mine and not rebuild
                else fn.project_cost(p.key, cap)
            )
            if mine and not rebuild:
                key = fn.built_key(p.key, mine["generation"])
            earns = fn.project_money(
                key, average, money.market, fans, revenue, row["ticket_price"]
            )
            blocked = None
            if not mine or rebuild:
                if is_stadium and current:
                    if current["year"] > year:
                        blocked = "Your new stadium is going up"
                    elif fn.STADIUM_TIERS.index(p.key) < tier_now:
                        blocked = "Below your stadium's tier"
                    elif not can_replace:
                        blocked = f"Can be replaced from {replace_from}"
                elif not mine:
                    blocker = fn.blocked_by(p.key, built)
                    if blocker:
                        blocked = (
                            "Replaced by your new stadium"
                            if blocker in fn.STADIUM_TIERS
                            else f"Ruled out by your {fn.project(blocker).name.lower()}"
                        )
            orderable = (not mine or rebuild) and not blocked
            out.append(
                {
                    "key": p.key,
                    "name": p.name,
                    "what": p.what,
                    "cost": cost,
                    "earns": earns,
                    "fans": round(p.fans * fn.rebuild_mult(key)),
                    "seats": p.capacity,
                    "value": fn.project_value(
                        key, average, money.market, fans, revenue, row["ticket_price"]
                    ),
                    "payback": fn.payback(cost, earns),
                    "built": mine["year"] if mine else None,
                    "build": p.build,
                    "stadium": is_stadium,
                    "generation": generation if orderable else None,
                    "rebuild": bool(rebuild and orderable),
                    "opens": year + p.build,
                    "blocked": blocked,
                    "short": fn.can_build(balance, cost, cap, p.key)
                    if orderable
                    else 0,
                    "waiting": orderable and this_season >= fn.BALLPARK_PER_SEASON,
                }
            )
        return out

    def build(self, league_id: str, team_id: str, year: int, key: str) -> str | None:
        """The owner builds a ballpark project, opening this season, from
        their bank (the caller checks it's between seasons). Returns why
        not, or None when it's built."""
        offer = next(
            (
                o
                for o in self.ballpark_offers(league_id, team_id, year)
                if o["key"] == key
            ),
            None,
        )
        if offer is None:
            return "That isn't a ballpark project."
        if offer["blocked"]:
            return f"{offer['blocked']}."
        if offer["built"] is not None and not offer["rebuild"]:
            if offer["built"] > year:
                return f"Your {offer['name'].lower()} opens in {offer['built']}."
            return f"Your {offer['name'].lower()} opened in {offer['built']}."
        if offer["waiting"]:
            return "One ballpark project a season: this one waits until next offseason."
        if offer["short"]:
            return (
                "Your owner won't dip that far into savings: they need "
                f"{format_salary(offer['short'])} more in the bank first."
            )
        self._add_project(
            league_id, team_id, year, key, offer["cost"], offer["generation"] or 1
        )
        return None

    def _add_project(
        self,
        league_id: str,
        team_id: str,
        year: int,
        key: str,
        cost: int,
        generation: int = 1,
    ) -> None:
        """Order a project this season; it opens once it's built."""
        p = fn.project(key)
        opens = year + (p.build if p else 0)
        self.conn.execute(
            """INSERT INTO ballpark_projects
                   (league_id, team_id, project, year, ordered, cost, generation)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (league_id, team_id, project, generation) DO NOTHING""",
            (league_id, team_id, key, opens, year, cost, generation),
        )

    def _ai_ballparks(
        self, league_id: str, year: int, team_ids: list[str], cap: int
    ) -> None:
        """AI GMs ask for a ballpark project when their owner can pay for
        it: the best payback for their market, more often for owners who
        spend."""
        if not team_ids:
            return
        banks = self.banks(league_id)
        spending = self._spending(league_id)
        for t in team_ids:
            if t not in banks:
                continue
            chance = 0.25 + 0.5 * spending.get(t, 50) / 100
            if random.Random(f"park:{league_id}:{t}:{year}").random() > chance:
                continue
            best = None
            for o in self.ballpark_offers(league_id, t, year):
                if o["generation"] is None or o["short"] or o["waiting"]:
                    continue
                seasons = fn.payback(o["cost"], o["value"])
                if seasons is None:
                    continue
                seasons += o["build"]  # nothing comes in while it goes up
                if best is None or seasons < best[0]:
                    best = (seasons, o)
            if best:
                o = best[1]
                self._add_project(
                    league_id, t, year, o["key"], o["cost"], o["generation"]
                )

    # ── Sponsors ─────────────────────────────────────────────────────────────

    def _series_won(self, season_id: str | None, results: dict) -> dict[str, int]:
        """Playoff series each team has won in a season: every series it
        played past its first, and the Finals for the champion (results:
        _results for the season)."""
        if not season_id:
            return {}
        out: dict[str, int] = {}
        for r in self.conn.execute(
            """SELECT team_id, COUNT(DISTINCT series_id) AS n FROM (
                   SELECT home_team_id AS team_id, series_id FROM games
                   WHERE season_id = %s AND series_id IS NOT NULL
                   UNION ALL
                   SELECT away_team_id, series_id FROM games
                   WHERE season_id = %s AND series_id IS NOT NULL
               ) x GROUP BY team_id""",
            (season_id, season_id),
        ).fetchall():
            out[r["team_id"]] = max(0, int(r["n"]) - 1)
        for t, r in results.items():
            if r.get("champion"):
                out[t] = out.get(t, 0) + 1
        return out

    def sponsors(
        self, league_id: str, year: int, team_ids: list[str] | None = None
    ) -> dict[str, dict]:
        """Each team's sponsor deal this season, by team id
        (src/league/finances.py sponsor_money): the offer it took, what Steady
        pays, and what the deal pays on the season so far (an Incentive deal's
        wins at today's win %). Empty without budgets."""
        rows = {
            r["team_id"]: r["sponsor_deal"]
            for r in self.conn.execute(
                """SELECT team_id, sponsor_deal FROM team_budgets
                   WHERE league_id = %s AND year = %s""",
                (league_id, year),
            ).fetchall()
        }
        if not rows:
            return {}
        ids = [t for t in rows if team_ids is None or t in team_ids]
        average = self._average_revenue(league_id, year)
        money = self._team_money(league_id, year, ids)
        last: dict[str, float] = {}
        for season_id in self._past_seasons(league_id, year, 1):
            for t, r in self._results(league_id, season_id).items():
                if "win_pct" in r:
                    last[t] = r["win_pct"]
        season_id = self._season_id(league_id, year)
        now = self._results(league_id, season_id) if season_id else {}
        rounds = self._series_won(season_id, now)
        out = {}
        for t in ids:
            steady = fn.sponsor_steady(average, money[t].market)
            kind = fn.sponsor_kind(rows[t], last.get(t))
            r = now.get(t, {})
            out[t] = {
                "kind": kind,
                "picked": rows[t] in fn.SPONSOR_KINDS,
                "steady": steady,
                "last_win_pct": last.get(t),
                "win_pct": r.get("win_pct", 0.5),
                "playoffs": bool(r.get("playoffs")),
                "rounds": rounds.get(t, 0),
                **fn.sponsor_money(
                    steady,
                    kind,
                    r.get("win_pct", 0.5),
                    bool(r.get("playoffs")),
                    rounds.get(t, 0),
                ),
            }
        return out

    def set_sponsor(self, league_id: str, team_id: str, year: int, kind: str) -> None:
        """Take a sponsor offer for the season (the caller checks it's
        allowed)."""
        self.conn.execute(
            """UPDATE team_budgets SET sponsor_deal = %s
               WHERE league_id = %s AND team_id = %s AND year = %s""",
            (fn.sponsor_kind(kind), league_id, team_id, year),
        )

    # ── Merchandise ──────────────────────────────────────────────────────────

    def _season_any(self, league_id: str, year: int) -> str | None:
        """The league's season in this year, a backstory one too."""
        row = self.conn.execute(
            """SELECT s.id FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s AND s.year = %s
               ORDER BY s.is_backstory LIMIT 1""",
            (league_id, year),
        ).fetchone()
        return row["id"] if row else None

    def _all_stars(self, season_id: str | None) -> set[str]:
        if not season_id:
            return set()
        return {
            r["player_id"]
            for r in self.conn.execute(
                "SELECT player_id FROM all_stars WHERE season_id = %s",
                (season_id,),
            ).fetchall()
        }

    def _games(self, season_id: str | None, team_ids=None) -> dict[tuple, int]:
        """{(player_id, team_id): regular season games} in a season."""
        if not season_id:
            return {}
        rows = self.conn.execute(
            """SELECT player_id, team_id,
                      SUM(GREATEST(bat_games_played, pitch_games_played)) AS n
               FROM player_season_stats
               WHERE season_id = %s AND NOT is_postseason
                 AND (%s::TEXT[] IS NULL OR team_id = ANY(%s::TEXT[]))
               GROUP BY player_id, team_id""",
            (season_id, team_ids, team_ids),
        ).fetchall()
        return {
            (r["player_id"], r["team_id"]): int(r["n"] or 0) for r in rows if r["n"]
        }

    def sellers(
        self, league_id: str, year: int, only: set[str] | None = None
    ) -> dict[str, list[fn.Seller]]:
        """Who sells jerseys for each team this season (or just these
        teams), by team id: everyone who played for it, by the share of his
        games he played there, and anyone on its big league roster who
        hasn't played anywhere yet. A team with no 26-man picked (in the
        offseason, saving the Roster tab leaves everyone on the 40-man until
        Opening Day) counts its 40-man instead, so the offseason estimate
        isn't just its Hall of Famers."""
        from src.api.services.icons import _grades

        teams = self._team_ids(league_id)
        season_id = self._season_id(league_id, year)
        games = self._games(season_id, teams)
        rows = self.conn.execute(
            """SELECT tp.player_id, tp.team_id, ps.status FROM team_players tp
               JOIN player_status ps ON ps.player_id = tp.player_id
               WHERE tp.team_id = ANY(%s) AND ps.status IN ('26man', '40man')""",
            (teams,),
        ).fetchall()
        picked = {r["team_id"] for r in rows if r["status"] == "26man"}
        roster = {
            r["player_id"]: r["team_id"]
            for r in rows
            if r["status"] == "26man" or r["team_id"] not in picked
        }
        played: dict[str, dict[str, int]] = {}
        for (p, t), n in games.items():
            played.setdefault(p, {})[t] = n
        for p, t in roster.items():
            if p not in played:
                played[p] = {t: 1}
        if only is not None:
            played = {p: bt for p, bt in played.items() if set(bt) & only}
        before: dict[str, set[str]] = {}
        for (p, t), _n in self._games(self._season_any(league_id, year - 1)).items():
            before.setdefault(p, set()).add(t)
        grades = _grades(self.conn, list(played)) if played else {}
        stars = self._all_stars(season_id)
        if not stars:
            # Until this season's All-Stars are picked, last season's are
            # expected back, so the estimate isn't far under what the
            # season ends up selling (Josh, 2026-11-11).
            stars = self._all_stars(self._season_any(league_id, year - 1))
        winners: set[str] = set()
        if season_id:
            winners = {
                r["player_id"]
                for r in self.conn.execute(
                    """SELECT player_id FROM season_awards
                       WHERE season_id = %s AND award = ANY(%s)
                         AND player_id IS NOT NULL""",
                    (season_id, list(fn.MERCH_AWARDS)),
                ).fetchall()
            }
        out: dict[str, list[fn.Seller]] = {}
        # Hall of Famers sell retro jerseys for the team they went in for,
        # from the season after they're elected (src/league/finances.py).
        for r in self.conn.execute(
            """SELECT hb.player_id, hb.team_id, he.year FROM hall_ballot hb
               JOIN hall_elections he ON he.season_id = hb.season_id
               WHERE hb.league_id = %s AND hb.outcome = 'elected'
                 AND he.year < %s AND hb.team_id = ANY(%s)""",
            (league_id, year, list(only) if only is not None else teams),
        ).fetchall():
            out.setdefault(r["team_id"], []).append(
                fn.Seller(
                    player_id=r["player_id"],
                    grade=fn.HALL_GRADE,
                    share=1.0,
                    new=r["year"] == year - 1,
                )
            )
        for p, by_team in played.items():
            grade = grades.get(p)
            if grade not in fn.MERCH_BY_GRADE:
                continue
            total = sum(by_team.values())
            last = before.get(p, set())
            for t, n in by_team.items():
                if only is not None and t not in only:
                    continue
                # New to the team (a new jersey): he played for someone
                # else last season, or, in his first season, for someone
                # else earlier this one before landing here.
                new = bool(last - {t}) or (
                    not last and bool(set(by_team) - {t}) and roster.get(p) == t
                )
                out.setdefault(t, []).append(
                    fn.Seller(
                        player_id=p,
                        grade=grade,
                        share=n / total if total else 1.0,
                        all_star=p in stars,
                        award=p in winners,
                        new=new,
                    )
                )
        return out

    def merchandise(self, league_id: str, year: int, team_ids=None) -> dict[str, dict]:
        """Each team's (or these teams') merchandise money this season, by
        team id: {"total", "sellers": [(Seller, amount), best first]}
        (src/league/finances.py merchandise). Empty without budgets."""
        if not self.for_league(league_id, year):
            return {}
        teams = self._team_ids(league_id)
        only = None if team_ids is None else set(team_ids)
        if only is not None:
            teams = [t for t in teams if t in only]
        cap = self.cap(league_id, year)
        money = self._team_money(league_id, year, teams)
        fans_before = {
            r["team_id"]: r["fans_before"]
            for r in self.conn.execute(
                "SELECT team_id, fans_before FROM team_budgets"
                " WHERE league_id = %s AND year = %s",
                (league_id, year),
            ).fetchall()
        }
        levels = self.league_levels(league_id, year)
        sellers = self.sellers(league_id, year, only)
        out = {}
        for t in teams:
            fans = fans_before.get(t)
            fans = money[t].fans if fans is None else fans
            total, parts = fn.merchandise(
                sellers.get(t, []),
                cap,
                money[t].market,
                fans,
                levels.get(t, {}).get("marketing"),
            )
            out[t] = {"total": total, "sellers": parts}
        return out

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
                      fans_before, ticket_price, popularity_revenue,
                      broadcast_revenue, merch_revenue, sponsor_revenue,
                      sponsor_deal, ballpark_revenue, crowd_revenue
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
            extra: dict = {"sellers": [], "sponsor_deal": None}
            cap = int(mine["cap"]) if mine["cap"] else self.cap(league_id, y)
            money = self._team_money(league_id, y, list(league_rows))
            revenue = self._revenues(league_id, y, league_rows, money, cap)
            average = sum(revenue.values()) / len(revenue)
            per_game = fn.playoff_gate(average, 1)
            fans = mine["fans_before"]
            fans = money[team_id].fans if fans is None else fans
            if done:
                gate = int(mine["playoff_revenue"] or 0)
                if mine["sponsor_deal"]:
                    extra["sponsor_deal"] = {"kind": mine["sponsor_deal"]}
                line = dict(
                    playoff_gate=gate,
                    home_playoff_games=round(gate / per_game) if per_game else 0,
                    popularity=int(mine["popularity_revenue"] or 0),
                    broadcast=int(mine["broadcast_revenue"] or 0),
                    merchandise=int(mine["merch_revenue"] or 0),
                    sponsor=int(mine["sponsor_revenue"] or 0),
                    ballpark=int(mine["ballpark_revenue"] or 0),
                    crowds=int(mine["crowd_revenue"] or 0),
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
                deal = self.broadcast_deal(league_id, team_id, y)
                sold = self.merchandise(league_id, y, [team_id]).get(team_id)
                sponsor = self.sponsors(league_id, y, [team_id]).get(team_id)
                extra = {
                    "sellers": sold["sellers"] if sold else [],
                    "sponsor_deal": sponsor,
                }
                line = dict(
                    ballpark=fn.ballpark_money(
                        self.ballparks(league_id, y).get(team_id, ()),
                        average,
                        market,
                        fans,
                        revenue[team_id],
                        mine["ticket_price"],
                    ),
                    sponsor=sponsor["total"] if sponsor else 0,
                    crowds=self._crowd_money(
                        self.crowds(league_id, y, [team_id]).get(team_id),
                        fn.ticket_revenue(revenue[team_id], mine["ticket_price"]),
                    ),
                    broadcast=deal["amount"] if deal else 0,
                    merchandise=sold["total"] if sold else 0,
                    minor_league=farms.get(team_id, 0),
                    farm_help=bg.average_farm(farms.values()),
                    playoff_gate=fn.playoff_gate(average, games),
                    home_playoff_games=games,
                    popularity=fn.popularity_money(average, fans),
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
                        average_revenue=average,
                        **line,
                    ),
                    "deal": self.deal_in(league_id, team_id, y),
                    **extra,
                }
            )
        return out

    def projected(self, league_id: str, year: int) -> dict[str, dict]:
        """Each team's revenue (with the playoff gate so far) and profit for
        the season, by team id, as the Budget tab projects them until the
        books close (books): today's payroll, tax and tax share for the
        year. Also fan interest coming in (fans_before) and where the season
        so far would leave it (fans_after). Empty without budgets."""
        rows = {
            r["team_id"]: r
            for r in self.conn.execute(
                """SELECT team_id, cap, revenue, fans_before, ticket_price
                   FROM team_budgets WHERE league_id = %s AND year = %s""",
                (league_id, year),
            ).fetchall()
        }
        if not rows:
            return {}
        first = next(iter(rows.values()))
        cap = int(first["cap"]) if first["cap"] else self.cap(league_id, year)
        money = self._team_money(league_id, year, list(rows))
        revenue = self._revenues(league_id, year, rows, money, cap)
        average = sum(revenue.values()) / len(revenue)
        costs = self._fixed_costs(average, cap)
        payrolls = {t: self.contracts.payroll(t, year) for t in rows}
        shares = bg.tax_shares(payrolls, cap)
        farms = self._minor_leagues(league_id, year, list(rows))
        farm_help = bg.average_farm(farms.values())
        levels = self.league_levels(league_id, year)
        season_id = self._season_id(league_id, year)
        results = self._results(league_id, season_id) if season_id else {}
        deals = self.broadcast_deals(league_id, year)
        merch = self.merchandise(league_id, year)
        sponsors = self.sponsors(league_id, year)
        parks = self.ballparks(league_id, year)
        crowds = self.crowds(league_id, year)
        out = {}
        for t, r in rows.items():
            fans = money[t].fans if r["fans_before"] is None else r["fans_before"]
            games = results.get(t, {}).get("home_playoff_games", 0)
            gate = fn.playoff_gate(average, games)
            b = fn.books(
                revenue=revenue[t],
                market=money[t].market,
                fans=fans,
                gate_per_game=fn.playoff_gate(average, 1),
                costs=costs,
                ticket_price=r["ticket_price"],
                minor_league=farms.get(t, 0),
                farm_help=farm_help,
                playoff_gate=gate,
                home_playoff_games=games,
                popularity=fn.popularity_money(average, fans),
                broadcast=deals[t]["amount"] if t in deals else 0,
                merchandise=merch[t]["total"] if t in merch else 0,
                sponsor=sponsors[t]["total"] if t in sponsors else 0,
                crowds=self._crowd_money(
                    crowds.get(t), fn.ticket_revenue(revenue[t], r["ticket_price"])
                ),
                ballpark=fn.ballpark_money(
                    parks.get(t, ()),
                    average,
                    money[t].market,
                    fans,
                    revenue[t],
                    r["ticket_price"],
                ),  # fmt: skip
                tax_share=shares.get(t, 0),
                payroll=payrolls[t],
                front_office=(
                    bg.front_office_cost(cap, levels[t]) if levels.get(t) else 0
                ),
                luxury_tax=bg.luxury_tax(payrolls[t], cap),
            )
            res = results.get(t, {})
            out[t] = {
                "revenue": revenue[t] + gate,
                "profit": b["profit"],
                # Where fan interest is headed if the season ends like this
                # (the books move it only when they close).
                "fans_before": fans,
                "fans_after": fn.fans_after(
                    fans,
                    res.get("win_pct", 0.5),
                    res.get("playoffs", False),
                    res.get("champion", False),
                    res.get("all_stars", 0),
                    r["ticket_price"],
                    levels.get(t, {}).get("marketing"),
                    fn.ballpark_fans(parks.get(t, ())),
                ),
            }
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
