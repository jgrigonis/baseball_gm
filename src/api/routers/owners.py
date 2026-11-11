# src/api/routers/owners.py
#
# The Owner tab: the GM's owner (src/api/services/owners.py) and every
# team's owner in the league. Only what GMs may see: names, bios,
# archetypes and what each archetype wants, never a number. Admins also get
# the numbers behind their owner's mood (owner_debug).

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from src.api.dependencies import DB, GMOrViewer, IsHTMX, User
from src.api.services import owner_debug, owner_office, owners
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/owner", response_class=HTMLResponse)
def owner_tab(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
):
    ctx = _shell_ctx(request, db, gm, league_id, "owner", user)
    team_id = gm.get("team_id") if gm and not ctx.get("is_viewer") else None
    if team_id:
        owner_office.catch_up(db, league_id)  # anything due, e.g. the preseason memo
    ctx["my_owner"] = owners.card(db, league_id, team_id) if team_id else None
    if ctx["my_owner"]:
        ctx["office"] = owner_office.office(db, league_id, team_id, gm["id"])
        ctx["owner_unseen"] = 0  # just read
        if ctx.get("is_admin"):
            ctx["owner_debug"] = owner_debug.explain(db, league_id, team_id)
    year = ContractRepository(db).current_year(league_id)
    if ctx["my_owner"] and year is not None:
        standing = BudgetRepository(db).standing(league_id, team_id, year)
        if standing:
            ctx["my_budget"] = {"year": year, **standing}
    ctx["owners"] = owners.league_table(db, league_id)
    ctx["my_team_id"] = team_id
    ctx["archetypes"] = owners.archetype_guide()
    db.commit()  # a league from before owners gets its owners on first look
    return tab_response(request, htmx, "dashboard/partials/owner.html", ctx)
