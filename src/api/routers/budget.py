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


def _render(request, htmx, league_id, db, user, gm, error=None, saved=False):
    ctx = _shell_ctx(request, db, gm, league_id, "budget", user)
    ctx["fo_error"] = error
    ctx["fo_saved"] = saved
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
    ctx["rules"] = {
        "tax_pct": round(bg.LUXURY_TAX_RATE * 100),
        "growth_pct": round(bg.CAP_GROWTH * 100),
        "pull_pct": round(bg.BANK_PULL * 100),
        "swing_pct": round(bg.BANK_SWING * 100),
        "margin_pct": round(bg.HARD_MARGIN * 100),
        "minor_pay_text": format_salary(
            round(bg.MINOR_LEAGUE_PAY * budgets.salary_scale(league_id, year))
            if year is not None
            else bg.MINOR_LEAGUE_PAY
        ),
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
                else r["revenue"] + (r["playoff_revenue"] or 0)
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
    db.commit()  # banks open on first look
    return tab_response(request, htmx, "dashboard/partials/budget.html", ctx)
