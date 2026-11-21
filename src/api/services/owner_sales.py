# src/api/services/owner_sales.py
#
# Owners in the red (Josh, 2026-11-21: "big negative banks should trigger
# some kind of event, not that we have to stop it algorithmically"). When the
# playoffs end and every season's profit is in the bank (BudgetRepository
# .banks), settle() looks at each owner's balance:
#
# - Below zero: the owner warns the GM in the Owner tab (key red:<season>)
#   that past budget.sale_line they'll have to sell.
# - Past the sale line (budget.SALE_DEBT of the cap in the red): the owner
#   sells the team. A buyer is drawn from the owner library like any owner
#   (owners.choose, tilted by market, never one already in the league or
#   one who sold out of it), brings a fresh bank (budget.starting_bank by
#   their Spending) and starts judging the next season. The GM keeps the job
#   and starts over with them at their grace level, like an admin's owner
#   change (owners.change). The debt goes with the old owner; payments still
#   owed on a stadium going up come with the team. owner_sales remembers it
#   for the news and the Budget tab's bank history.
#
# Safe to run twice: a team sells at most once a season, and messages are
# written once under their key.

from __future__ import annotations

import random

from src.api.services import owner_office
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.owner_repo import OwnerRepository
from src.api.services import owners as owner_service
from src.league import budget as bg
from src.league import owners
from src.player.contracts import format_salary


def _red(amount: int) -> str:
    return format_salary(abs(amount), "down")


def settle(conn, league_id: str, season_id: str, year: int) -> list[dict]:
    """Warn every owner whose bank finished the season in the red, and sell
    the teams too far in it. Returns the sales (owner_sales rows)."""
    budgets = BudgetRepository(conn)
    if not budgets.enabled(league_id):
        return []
    cap = budgets.cap(league_id, year)
    if not cap:
        return []
    seats = OwnerRepository(conn).in_league(league_id)
    gms = owner_office._gms(conn, league_id)
    names = owner_office._team_names(conn, seats)
    done = {s["team_id"] for s in budgets.sales(league_id) if s["year"] == year}
    line = bg.sale_line(cap)
    sales = []
    for team_id, bank in sorted(budgets.banks(league_id).items()):
        seat = seats.get(team_id)
        if not seat or team_id in done or bank["balance"] >= 0:
            continue
        gm = gms.get(team_id)
        if not bg.must_sell(bank["balance"], cap):
            if gm:
                owner_office._write(
                    conn, league_id, team_id, gm["id"], season_id,
                    f"red:{season_id}", "bank",
                    f"We finished {year} {_red(bank['balance'])} in the red, and "
                    f"that's my money. I can't keep covering losses like this: "
                    f"if a season ends with the bank more than {_red(line)} in "
                    f"the red, I'll have to sell the club.",
                    None, None,
                )  # fmt: skip
            continue
        sale = _sell(conn, league_id, team_id, year, seat, bank, cap)
        if sale is None:
            continue
        sales.append(sale)
        if gm:
            owner_office._write(
                conn, league_id, team_id, gm["id"], season_id,
                f"sold:{season_id}", "sale",
                f"{sale['old_name']} has sold me the {names.get(team_id, 'club')}, "
                f"{_red(sale['debt'])} in the red. That debt leaves with them: "
                f"I'm putting {format_salary(sale['new_bank'], 'down')} in the "
                f"bank to start fresh. You keep your job, but you work for me "
                f"now, and I'll judge you on what you do from {year + 1} on.",
                None, None,
            )  # fmt: skip
    return sales


def _sell(conn, league_id, team_id, year, seat, bank, cap) -> dict | None:
    repo = OwnerRepository(conn)
    budgets = BudgetRepository(conn)
    taken = {o["owner_id"] for o in repo.in_league(league_id).values()}
    taken |= {s["old_owner_id"] for s in budgets.sales(league_id)}
    pool = [o for o in repo.pool() if o["id"] not in taken] or [
        o for o in repo.pool() if o["id"] != seat["owner_id"]
    ]
    market = owner_service.market_of(
        conn.execute(
            "SELECT city, mascot FROM teams WHERE id = %s", (team_id,)
        ).fetchone()
    )
    rng = random.Random(f"{league_id}-sale-{team_id}-{year}")
    buyer = owners.choose(pool, set(), market, rng)
    if buyer is None:
        return None
    traits = owners.clean_traits((repo.get(buyer["id"]) or {}).get("traits") or {})
    new_bank = bg.starting_bank(cap, traits["spending"])
    conn.execute(
        """INSERT INTO owner_sales
               (league_id, team_id, year, old_owner_id, new_owner_id,
                old_bank_start, old_bank_year, debt, new_bank)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (league_id, team_id, year, seat["owner_id"], buyer["id"],
         bank["start"], bank["since"], bank["balance"], new_bank),
    )  # fmt: skip
    conn.execute(
        """UPDATE team_owners
           SET owner_id = %s, since_year = %s, bank_start = %s, bank_year = %s
           WHERE league_id = %s AND team_id = %s""",
        (buyer["id"], year + 1, new_bank, year + 1, league_id, team_id),
    )
    conn.execute(
        "DELETE FROM owner_moods WHERE league_id = %s AND team_id = %s",
        (league_id, team_id),
    )
    return {
        "team_id": team_id,
        "year": year,
        "old_owner_id": seat["owner_id"],
        "old_name": seat["name"],
        "new_owner_id": buyer["id"],
        "new_name": buyer["name"],
        "debt": bank["balance"],
        "new_bank": new_bank,
    }
