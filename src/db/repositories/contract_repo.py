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
he's released. A guaranteed one (he's played a game on the 40-man under it,
or he signed it as a free agent) stays on the releasing team's payroll as dead
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
# Playing a game on the 40-man under a deal guarantees it (just being put
# there doesn't, Josh 2026-11-09). Until then the deal is on the payroll
# while he's on the 40-man, but releasing him costs nothing.
FORTY_MAN_STATUSES = ("26man", "40man")

# A deal still his in a season: not released, or released after it.
IN_FORCE = "(c.released_year IS NULL OR c.released_year > %s)"


def _years_left(row: dict, year: int) -> int:
    return row["start_year"] + row["years"] - year


def view(row: dict | None, year: int, scale: float = 1.0) -> dict | None:
    """A contract for display: salary text, which year of how many, and the
    last season it covers. A minor leaguer whose deal isn't on the payroll
    (row["on_payroll"] false: never played a game on the 40-man) is paid
    the minor league salary instead (farm_pay_text; scale: the league's
    salary_scale)."""
    if row is None:
        return None
    farm = row.get("on_payroll") is False
    return {
        "farm": farm,
        "farm_pay_text": (ct.format_salary(ct.minors_salary(scale)) if farm else None),
        "kind": row["kind"],
        "salary": row["salary"],
        "salary_text": ct.format_salary(row["salary"]),
        "years": row["years"],
        "year_of": year - row["start_year"] + 1,
        "years_left": _years_left(row, year),
        "through": row["start_year"] + row["years"] - 1,
        "pick_number": row.get("pick_number"),
        "signing_bonus_text": (
            ct.format_salary(row["signing_bonus"]) if row.get("signing_bonus") else None
        ),
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
        """Each player's deal this season, by player id. `on_payroll`: what
        it adds to his team's payroll, a guaranteed deal or one of a player
        on the 40-man (guaranteed once he plays a game there)."""
        ids = list(player_ids)
        if not ids:
            return {}
        rows = self.conn.execute(
            f"""
            SELECT c.*,
                   (c.guaranteed OR COALESCE(ps.status = ANY(%s), FALSE))
                       AS on_payroll
            FROM player_contracts c
            LEFT JOIN player_status ps ON ps.player_id = c.player_id
            WHERE c.player_id = ANY(%s)
              AND c.start_year <= %s AND c.start_year + c.years > %s
              AND {IN_FORCE}
            ORDER BY c.start_year
            """,
            (list(FORTY_MAN_STATUSES), ids, year, year, year),
        ).fetchall()
        return {r["player_id"]: dict(r) for r in rows}

    def deals_through(self, player_ids, year: int, last: int) -> dict[str, list]:
        """Each player's deals in force that cover any season from year
        through last, by player id, oldest first."""
        ids = list(player_ids)
        if not ids:
            return {}
        rows = self.conn.execute(
            f"""
            SELECT c.player_id, c.start_year, c.years, c.salary FROM player_contracts c
            WHERE c.player_id = ANY(%s)
              AND c.start_year <= %s AND c.start_year + c.years > %s
              AND {IN_FORCE}
            ORDER BY c.start_year
            """,
            (ids, last, year, year),
        ).fetchall()
        out: dict[str, list] = {}
        for r in rows:
            out.setdefault(r["player_id"], []).append(dict(r))
        return out

    def history(self, player_id: str) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM player_contracts WHERE player_id = %s ORDER BY start_year",
            (player_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def payroll(self, team_id: str, year: int) -> int:
        """What the team owes this season: the deals of its 40-man and the
        guaranteed deals of the rest it holds, plus dead money for players
        it released."""
        row = self.conn.execute(
            f"""
            SELECT COALESCE(SUM(c.salary), 0) AS total
            FROM team_players tp
            JOIN player_status ps ON ps.player_id = tp.player_id
            JOIN player_contracts c ON c.player_id = tp.player_id
            WHERE tp.team_id = %s AND ps.status = ANY(%s)
              AND (c.guaranteed OR ps.status = ANY(%s))
              AND c.start_year <= %s AND c.start_year + c.years > %s
              AND {IN_FORCE}
            """,
            (
                team_id,
                list(SIGNED_STATUSES),
                list(FORTY_MAN_STATUSES),
                year,
                year,
                year,
            ),
        ).fetchone()
        return int(row["total"]) + self.dead_money(team_id, year)

    def minor_league_pay(
        self, team_ids, year: int, each: int = ct.MINORS_SALARY
    ) -> dict[str, int]:
        """What each team pays this season to the minor leaguers who aren't
        on its payroll (deals never guaranteed: never played on the 40-man), by
        team id: each of them earns `each`, the minor league salary, not his
        deal's (src/player/contracts.py minors_salary), plus the signing
        bonuses of the players it drafted for this season (signing_bonuses).
        Not payroll or the cap, but it counts against the owner's budget
        (src/league/budget.py)."""
        ids = list(team_ids)
        out = dict.fromkeys(ids, 0)
        if not ids:
            return out
        rows = self.conn.execute(
            f"""
            SELECT tp.team_id, COUNT(DISTINCT tp.player_id) AS n
            FROM team_players tp
            JOIN player_status ps ON ps.player_id = tp.player_id
            JOIN player_contracts c ON c.player_id = tp.player_id
            WHERE tp.team_id = ANY(%s) AND ps.status = 'minors'
              AND NOT c.guaranteed
              AND c.start_year <= %s AND c.start_year + c.years > %s
              AND {IN_FORCE}
            GROUP BY tp.team_id
            """,
            (ids, year, year, year),
        ).fetchall()
        for r in rows:
            out[r["team_id"]] = int(r["n"] or 0) * each
        for team_id, bonus in self.signing_bonuses(ids, year).items():
            out[team_id] += bonus
        return out

    def signing_bonuses(self, team_ids, year: int) -> dict[str, int]:
        """What each team pays in signing bonuses this season: the players
        it drafted for it, paid once, even if he's since been released or
        traded. By team id, teams with none left out."""
        ids = list(team_ids)
        if not ids:
            return {}
        rows = self.conn.execute(
            """
            SELECT team_id, SUM(signing_bonus) AS total FROM player_contracts
            WHERE team_id = ANY(%s) AND start_year = %s AND signing_bonus > 0
            GROUP BY team_id
            """,
            (ids, year),
        ).fetchall()
        return {r["team_id"]: int(r["total"]) for r in rows}

    def dead_money(self, team_id: str, year: int) -> int:
        """This season's salary of the guaranteed deals the team released."""
        return sum(r["salary"] for r in self.dead_money_rows(team_id, year))

    def dead_money_rows(self, team_id: str, year: int) -> list[dict]:
        """Each released deal the team still pays this season: the player,
        his salary, and the last season it's owed."""
        # Once he signs elsewhere, his new salary comes off what's owed
        # (the offset, through the last season of his new deal).
        rows = self.conn.execute(
            """
            SELECT c.player_id, c.start_year + c.years - 1 AS through,
                   c.salary - CASE WHEN c.offset_through >= %s
                                   THEN LEAST(c.offset_salary, c.salary)
                                   ELSE 0 END AS salary,
                   c.salary AS full_salary,
                   p.first_name, p.last_name
            FROM player_contracts c
            JOIN players p ON p.id = c.player_id
            WHERE c.released_team_id = %s AND c.guaranteed
              AND c.released_year <= %s AND c.start_year + c.years > %s
            ORDER BY salary DESC
            """,
            (year, team_id, year, year),
        ).fetchall()
        return [dict(r) for r in rows if r["salary"] > 0]

    def apply_offset(
        self, player_id: str, year: int, salary: int, through: int
    ) -> None:
        """He signed elsewhere for this salary a season through that season:
        take it off what his old teams still owe him (full offset, Josh
        2026-11-05)."""
        self.conn.execute(
            """UPDATE player_contracts SET offset_salary = %s, offset_through = %s
               WHERE player_id = %s AND guaranteed AND released_year IS NOT NULL
                 AND start_year + years > %s""",
            (salary, through, player_id, year),
        )

    def claim(self, player_id: str, from_team_id: str, to_team_id: str) -> dict | None:
        """A team claimed him off waivers: it takes over the deal his old
        team released, so the old team owes nothing. Returns the deal."""
        row = self.conn.execute(
            """SELECT * FROM player_contracts
               WHERE player_id = %s AND released_team_id = %s
               ORDER BY start_year DESC, id DESC LIMIT 1""",
            (player_id, from_team_id),
        ).fetchone()
        if row is None:
            return None
        self.conn.execute(
            """UPDATE player_contracts
               SET released_year = NULL, released_team_id = NULL, team_id = %s
               WHERE id = %s""",
            (to_team_id, row["id"]),
        )
        return dict(row)

    def released_deal(self, player_id: str, from_team_id: str) -> dict | None:
        """The deal his old team released, for the claim confirm."""
        row = self.conn.execute(
            """SELECT * FROM player_contracts
               WHERE player_id = %s AND released_team_id = %s
               ORDER BY start_year DESC, id DESC LIMIT 1""",
            (player_id, from_team_id),
        ).fetchone()
        return dict(row) if row else None

    def guarantee_teams(self, team_ids) -> None:
        """These teams just played a game: the deals of everyone on their
        40-mans are now guaranteed."""
        ids = list(team_ids)
        if not ids:
            return
        rows = self.conn.execute(
            "SELECT player_id FROM team_players WHERE team_id = ANY(%s)", (ids,)
        ).fetchall()
        self.guarantee([r["player_id"] for r in rows])

    def guarantee(self, player_ids) -> None:
        """Make the deals of any of these players now on a 40-man
        guaranteed: his newest deal still in force. Called once he's played
        a game there (guarantee_teams), or re-signed while on it."""
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
                pick_number, guaranteed, signing_bonus
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                deal.signing_bonus,
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

        renewing = [r["player_id"] for r in rows if r["signed_before"]]
        happy.prepare_resign(renewing, self.seasons_signed(renewing, year - 1))
        arb = self.arbitration_seasons(renewing, year)
        unhappy_out: list[tuple[str, str]] = []

        signed = 0
        for r in rows:
            pid = r["player_id"]
            rng = random.Random(f"contract:{pid}:{year}")
            draft_year = r["draft_year"]
            if (
                not r["signed_before"]
                and draft_year is not None
                and draft_year <= year < draft_year + ct.rookie_years(pid)
            ):
                deal = ct.rookie_deal(
                    r["pick_number"], scale(draft_year), ct.rookie_years(pid)
                )
                self._insert(
                    pid, league_id, r["team_id"], deal, draft_year, r["pick_number"]
                )
                signed += 1
                continue

            p = records.get(pid)
            if p is None:
                continue
            start = year
            if not r["signed_before"]:
                kind = "pitcher" if p.is_pitcher() else "hitter"
                deal = ct.standard_deal(p.age, role_rating(p), kind, rng, scale(year))
                start -= ct.years_already_served(deal.years, rng)
            else:
                deal, wants_out = self.renewal(
                    p, year, happy, scale(year), arb.get(pid)
                )
                if wants_out:
                    unhappy_out.append((pid, r["team_id"]))
            self._insert(pid, league_id, r["team_id"], deal, start)
            signed += 1
        happy.request_trades(unhappy_out, year)
        # A 40-man player re-signing keeps a guaranteed deal, like the
        # offseason re-signs (src/api/services/offseason_fa.py). New deals
        # wait for a game on the 40-man.
        self.guarantee([r["player_id"] for r in rows if r["signed_before"]])
        return signed

    def renewal(
        self, p, year: int, happy, scale: float = 1.0, arb_season: int | None = None
    ) -> tuple[ct.Deal, bool]:
        """The new deal a player whose last one ran out signs from `year`,
        his mood worked in, and whether he wants a trade. The same price in
        the offseason's re-sign window as when he re-signs after the draft
        (src/api/services/offseason_fa.py). `happy` is a HappinessRepository
        that has had prepare_resign for him. arb_season: which season in the
        league the deal is for, when he came up on a rookie deal
        (arbitration_seasons); an arbitration season prices it as a share
        of his market price (src/player/contracts.py arbitration_deal)."""
        rng = random.Random(f"contract:{p.id}:{year}")
        kind = "pitcher" if p.is_pitcher() else "hitter"
        deal = ct.standard_deal(p.age, role_rating(p), kind, rng, scale)
        if arb_season is not None:
            deal = ct.arbitration_deal(deal, arb_season, scale) or deal
        return self._mood_terms(happy, p.id, None, deal, scale)

    @staticmethod
    def market_salary(p, year: int, scale: float = 1.0) -> int:
        """What a player's next deal from `year` would pay on the open
        market, before arbitration or his mood: the price renewal starts
        from."""
        rng = random.Random(f"contract:{p.id}:{year}")
        kind = "pitcher" if p.is_pitcher() else "hitter"
        return ct.standard_deal(p.age, role_rating(p), kind, rng, scale).salary

    def arbitration_seasons(self, player_ids, year: int) -> dict[str, int]:
        """For players who came up on a rookie deal in this league: which
        season in the league a new deal from `year` would be (his rookie
        deal's first season is 1). Others are left out: a league's starting
        players never go to arbitration."""
        ids = list(player_ids)
        if not ids:
            return {}
        rows = self.conn.execute(
            """SELECT DISTINCT ON (player_id) player_id, kind, start_year
               FROM player_contracts WHERE player_id = ANY(%s)
               ORDER BY player_id, start_year, created_at""",
            (ids,),
        ).fetchall()
        return {
            r["player_id"]: year - r["start_year"] + 1
            for r in rows
            if r["kind"] == "rookie"
        }

    def seasons_signed(self, player_ids, year: int) -> dict[str, int]:
        """Seasons each player has played under a deal in this league,
        through `year`: from the start of his first one."""
        ids = list(player_ids)
        if not ids:
            return {}
        rows = self.conn.execute(
            """SELECT player_id, MIN(start_year) AS first FROM player_contracts
               WHERE player_id = ANY(%s) GROUP BY player_id""",
            (ids,),
        ).fetchall()
        return {r["player_id"]: year - r["first"] + 1 for r in rows}

    def insert_deal(
        self, player_id, league_id, team_id, deal: ct.Deal, start_year, guaranteed=False
    ) -> None:
        self._insert(
            player_id, league_id, team_id, deal, start_year, guaranteed=guaranteed
        )

    @staticmethod
    def _mood_terms(happy, pid: str, team_id: str, deal: ct.Deal, scale: float = 1.0):
        """His new deal with his mood worked in: a discount when he's happy
        and loyal, more money for fewer years when he isn't."""
        mult, max_years, wants_out = happy.resign_terms(pid)
        years = deal.years if max_years is None else min(deal.years, max_years)
        salary = ct.round_salary(deal.salary * mult, scale)
        return ct.Deal(salary, years, deal.kind), wants_out
