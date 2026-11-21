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
#   their Spending) and starts judging the next season. They bring in their
#   own GM (Josh, 2026-11-21): the GM is fired (firing.py), unless the old
#   owner fired them already this season or the league has owner firing
#   off, when the GM keeps the job and starts over with the buyer at their
#   grace level, like an admin's owner change (owners.change). The debt goes with the old owner; payments still
#   owed on a stadium going up come with the team. owner_sales remembers it
#   for the news and the Budget tab's bank history.
#
# Safe to run twice: a team sells at most once a season, and messages are
# written once under their key.

from __future__ import annotations

import random

from src.api.services import firing, owner_office, owner_review
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
    league = conn.execute(
        "SELECT mode, owner_firing, is_practice FROM leagues WHERE id = %s",
        (league_id,),
    ).fetchone()
    fire = owner_review.firing_on(dict(league))
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
        if not gm:
            continue
        if fire and not _fired_this_season(conn, team_id, season_id):
            # The buyer brings in their own GM (Josh, 2026-11-21), unless the
            # old owner just let the last one go and hired this one.
            _fire(conn, league_id, season_id, year, gm, sale)
            continue
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


def _fired_this_season(conn, team_id: str, season_id: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM gm_firings WHERE team_id = %s AND season_id = %s",
            (team_id, season_id),
        ).fetchone()
    )


def _fire(conn, league_id, season_id, year, gm, sale) -> None:
    """The new owner lets the team's GM go (src/api/services/firing.py), with
    the season's record from the old owner's review and their own words for
    the fired banner."""
    row = conn.execute(
        """SELECT g.id AS gm_id, g.team_id, g.user_id, g.persona_id,
                  g.display_name, g.is_ai, t.city, t.mascot,
                  COALESCE(e.wins, 0) AS wins, COALESCE(e.losses, 0) AS losses
           FROM gms g
           JOIN teams t ON t.id = g.team_id
           LEFT JOIN gm_season_evaluations e
             ON e.gm_id = g.id AND e.season_id = %s
           WHERE g.id = %s""",
        (season_id, gm["id"]),
    ).fetchone()
    if not row:
        return
    r = dict(row) | {"owner_id": sale["new_owner_id"]}
    done = firing._fire(conn, league_id, season_id, year, r)
    conn.execute(
        """UPDATE gm_firings SET message = %s
           WHERE league_id = %s AND gm_id = %s AND season_id = %s""",
        (
            f"I've bought the club from {sale['old_name']}, "
            f"{_red(sale['debt'])} in the red, and I'm bringing in my own "
            f"people. Thank you for your work.",
            league_id, done["gm_id"], season_id,
        ),
    )  # fmt: skip
