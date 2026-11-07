# src/api/routers/budget.py
#
# The Budget tab (plans/budget.md, Q7): the GM's money this season (the
# league's cap, the owner's budget and hard limit, payroll and the luxury
# tax), the owner's bank, the front office (set once each offseason) and
# the team's money season by season. Only money: the owner's traits stay
# hidden, and front office levels are the GM's own. Not in Speed Blitz.


from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GM, ActiveLeague, IsHTMX, User
from src.db.locks import league_lock
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.league import budget as bg
from src.league import finances as fn
from src.player.contracts import format_salary
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])
# When front office levels can change: between seasons, from the draft to
# Opening Day. They're locked once the season starts.
FRONT_OFFICE_STATES = ("draft", "preseason")


def _money(amount) -> str | None:
    if amount is None:
        return None
    text = format_salary(abs(int(amount)))
    return f"-{text}" if amount < 0 else text


def _times(mult: float) -> str:
    return f"\u00d7{mult:.2f}"


def _books_view(b: dict) -> dict:
    """One season's money in and out (BudgetRepository.books), as text."""
    games = b["home_playoff_games"]
    money_in = [
        {
            "label": "Regular season",
            "amount": _money(b["revenue"]),
            "note": (
                f"{_money(b['base'])} league base"
                f" {_times(b['market_mult'])} {b['market_name'].lower()} market"
                f" {_times(b['fan_mult'])} fan interest {b['fans']}"
            ),
        },
        {
            "label": "Ticket prices",
            "amount": _money(b["tickets"]) if b["tickets"] else None,
            "note": f"{b['ticket_name']} ({b['ticket_price']} of 10)"
            + (f": {b['ticket_pct']:+g}% at the gate" if b["ticket_pct"] else ""),
            "bad": b["tickets"] < 0,
        },
        {
            "label": "Playoff gate",
            "amount": _money(b["playoff_gate"]) if b["playoff_gate"] else None,
            "note": (
                f"{games} home playoff game{'' if games == 1 else 's'}"
                f"{' so far' if b['projected'] else ''}"
                f" at {_money(b['gate_per_game'])} each"
                if games
                else f"{_money(b['gate_per_game'])} for each home playoff game"
            ),
        },
        {
            "label": "Popularity",
            "amount": _money(b["popularity"]) if b["popularity"] else None,
            "note": (
                f"Fan interest {b['fans']}: keen fans bring in extra money"
                if b["popularity"]
                else f"Earned once fan interest is over {b['popularity_from']}"
            ),
        },
        {
            "label": "Luxury tax share",
            "amount": _money(b["tax_share"]) if b["tax_share"] else None,
            "note": (
                "Your cut of the tax paid by teams over the cap"
                if b["tax_share"]
                else "Paid to teams under the cap when someone goes over"
            ),
        },
        {
            "label": "League farm help",
            "amount": _money(b["farm_help"]) if b["farm_help"] else None,
            "note": "The league covers an average farm's salaries",
        },
    ]
    money_out = [
        {"label": "Payroll", "amount": _money(b["payroll"]),
         "note": "Guaranteed salaries plus dead money"},
        {"label": "Front office", "amount": _money(b["front_office"]),
         "note": "Coaching, facilities, analytics and marketing"},
        {"label": "Minor leagues", "amount": _money(b["minor_league"]) if b["minor_league"] else None,
         "note": "Salaries of players off the 40-man"},
        {"label": "Luxury tax", "amount": _money(b["luxury_tax"]) if b["luxury_tax"] else None,
         "note": f"{round(bg.LUXURY_TAX_RATE * 100)}% of payroll over the cap", "bad": bool(b["luxury_tax"])},
        {"label": "Fixed costs", "amount": _money(b["costs"]),
         "note": "Ballpark, travel and staff, the same for every team"},
    ]  # fmt: skip
    if b["other"]:
        money_out.append(
            {"label": "Other costs", "amount": _money(b["other"]), "note": ""}
        )
    return {
        "year": b["year"],
        "projected": b["projected"],
        "money_in": money_in,
        "money_out": money_out,
        "total_in": _money(b["total_in"]),
        "total_out": _money(b["total_out"]),
        "profit": _money(b["profit"]),
        "loss": b["profit"] < 0,
    }


@router.get("/leagues/{league_id}/budget", response_class=HTMLResponse)
def budget_tab(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    return _render(request, htmx, league_id, db, user, gm)


@router.post("/leagues/{league_id}/budget/front-office", response_class=HTMLResponse)
def set_front_office(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
    _active: ActiveLeague,
    department: str = Form(...),
    level: int = Form(...),
):
    """Fund one department at a level. Only between seasons, and the owner
    won't pay for a raise past their hard limit."""
    team_id = gm.get("team_id")
    error = None
    with league_lock(db, league_id):
        league = LeagueRepository(db).get_by_id(league_id)
        budgets = BudgetRepository(db)
        year = ContractRepository(db).current_year(league_id)
        levels = budgets.levels(league_id, team_id, year) if year else {}
        if not levels or department not in bg.DEPARTMENT_KEYS:
            error = "This league has no front office budget."
        elif league["state"] not in FRONT_OFFICE_STATES:
            error = "The front office is set between seasons, from the draft to Opening Day."
        else:
            cap = budgets.cap(league_id, year)
            added = bg.level_cost(cap, level) - bg.level_cost(cap, levels[department])
            error = budgets.refusal(league_id, team_id, year, added)
            if not error:
                budgets.set_level(league_id, team_id, year, department, level)
        db.commit()
    return _render(request, htmx, league_id, db, user, gm, error, saved=not error)


@router.post("/leagues/{league_id}/budget/tickets", response_class=HTMLResponse)
def set_tickets(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
    _active: ActiveLeague,
    level: int = Form(...),
):
    """Set ticket prices for the season. Only between seasons, like the
    front office."""
    team_id = gm.get("team_id")
    error = None
    with league_lock(db, league_id):
        league = LeagueRepository(db).get_by_id(league_id)
        budgets = BudgetRepository(db)
        year = ContractRepository(db).current_year(league_id)
        if not year or budgets.ticket_price(league_id, team_id, year) is None:
            error = "This league has no ticket prices."
        elif league["state"] not in FRONT_OFFICE_STATES:
            error = (
                "Ticket prices are set between seasons, from the draft to Opening Day."
            )
        else:
            budgets.set_ticket_price(league_id, team_id, year, level)
        db.commit()
    return _render(
        request, htmx, league_id, db, user, gm,
        ticket_error=error, ticket_saved=not error,
    )  # fmt: skip


def _ticket_options() -> list[dict]:
    out = []
    for level in fn.TICKET_LEVELS:
        pct = round((fn.ticket_mult(level) - 1) * 100, 1)
        fans = fn.ticket_fans(level)
        out.append(
            {
                "level": level,
                "name": fn.ticket_name(level),
                "revenue": "no change" if not pct else f"{pct:+g}%",
                "fans": "no change" if not fans else f"{fans:+d}",
            }
        )
    return out


def _league_pay(db, seasons: list[dict], my_team: str | None) -> list[dict]:
    """Every team's payroll, luxury tax and tax share by season, for the
    league table on the Budget tab."""
    ids = list({t for s in seasons for t in s["teams"]})
    names = {
        r["id"]: r
        for r in db.execute(
            "SELECT id, city, mascot FROM teams WHERE id = ANY(%s)", (ids,)
        ).fetchall()
    }
    out = []
    for s in seasons:
        cap = s["cap"]
        rows = []
        for team_id, m in s["teams"].items():
            team = names.get(team_id) or {"city": "", "mascot": team_id}
            gap = m["payroll"] - cap
            rows.append(
                {
                    "city": team["city"],
                    "mascot": team["mascot"],
                    "mine": team_id == my_team,
                    "payroll": m["payroll"],
                    "payroll_text": _money(m["payroll"]),
                    "gap": gap,
                    "gap_text": (
                        f"{_money(gap)} over"
                        if gap > 0
                        else f"{_money(-gap)} under"
                        if gap < 0
                        else "At the cap"
                    ),
                    "over": gap > 0,
                    "tax": m["tax"],
                    "tax_text": _money(m["tax"]) if m["tax"] else None,
                    "share": m["share"],
                    "share_text": _money(m["share"]) if m["share"] else None,
                }
            )
        rows.sort(key=lambda r: -r["payroll"])
        out.append(
            {
                "year": s["year"],
                "projected": s["projected"],
                "cap_text": _money(cap),
                "rows": rows,
                "pool_text": _money(sum(r["tax"] for r in rows)),
                "over_count": sum(1 for r in rows if r["over"]),
            }
        )
    return out


def _render(
    request, htmx, league_id, db, user, gm, error=None, saved=False,
    ticket_error=None, ticket_saved=False,
):  # fmt: skip
    ctx = _shell_ctx(request, db, gm, league_id, "budget", user)
    ctx["fo_error"] = error
    ctx["fo_saved"] = saved
    ctx["ticket_error"] = ticket_error
    ctx["ticket_saved"] = ticket_saved
    team_id = gm.get("team_id")
    budgets = BudgetRepository(db)
    year = ContractRepository(db).current_year(league_id)
    standing = (
        budgets.standing(league_id, team_id, year)
        if team_id and year is not None
        else None
    )
    ctx["year"] = year
    ctx["money"] = standing
    bank = budgets.banks(league_id).get(team_id) if standing else None
    if bank:
        ctx["bank"] = {
            "balance_text": _money(bank["balance"]),
            "change_text": _money(bank["change"]),
            "start_text": _money(bank["start"]),
            "since": bank["since"],
            "up": bank["change"] >= 0,
            "empty": bank["balance"] <= 0,
        }
    if standing:
        cap = standing["cap"]
        levels = budgets.levels(league_id, team_id, year)
        ctx["front_office"] = [
            {
                "key": key,
                "label": label,
                "what": what,
                "level": levels[key],
                "options": [
                    {
                        "level": i,
                        "name": name,
                        "cost_text": format_salary(bg.level_cost(cap, i)),
                    }
                    for i, name in enumerate(bg.LEVELS)
                ],
            }
            for key, label, what in bg.DEPARTMENTS
        ]
        ctx["fo_open"] = ctx.get("league_state") in FRONT_OFFICE_STATES
        level = budgets.ticket_price(league_id, team_id, year)
        ctx["tickets"] = {"level": level, "options": _ticket_options()}
    ctx["rules"] = {
        "tax_pct": round(bg.LUXURY_TAX_RATE * 100),
        "pull_pct": round(bg.BANK_PULL * 100),
        "swing_pct": round(bg.BANK_SWING * 100),
        "margin_pct": round(bg.HARD_MARGIN * 100),
    }
    ctx["history"] = [
        {
            "year": r["year"],
            "cap": _money(r["cap"]),
            "budget": _money(r["budget"]),
            "payroll": _money(r["payroll"]),
            "revenue": _money(
                None
                if r["revenue"] is None or r["profit"] is None
                else fn.ticket_revenue(r["revenue"], r["ticket_price"])
                + (r["playoff_revenue"] or 0)
            ),
            "tax": _money(r["luxury_tax"]) if r["luxury_tax"] else None,
            "front_office": _money(r["front_office"]),
            "minor_league": _money(r["minor_league"]),
            "share": _money(r["tax_share"]) if r["tax_share"] else None,
            "profit": _money(r["profit"]),
            "loss": r["profit"] is not None and r["profit"] < 0,
            "fans": r["fans_after"],
            "bank": _money(r["bank_after"]),
        }
        for r in (budgets.history(league_id, team_id) if standing else [])
        if r["profit"] is not None
    ]
    ctx["books"] = [
        _books_view(b)
        for b in (budgets.books(league_id, team_id, year) if standing else [])
    ]
    ctx["league_pay"] = (
        _league_pay(db, budgets.league_payrolls(league_id, year), team_id)
        if standing
        else []
    )
    db.commit()  # banks open on first look
    return tab_response(request, htmx, "dashboard/partials/budget.html", ctx)
