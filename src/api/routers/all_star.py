# src/api/routers/all_star.py
#
# The All-Star tab: the ballot while voting is open, the All-Stars and the
# captains' draft after, then the All-Star Game (src/api/services/all_star.py).

from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.api.dependencies import DB, GM, ActiveLeague, GMOrViewer, IsHTMX, User
from src.api.services import all_star
from src.db.repositories.season_repo import SeasonRepository
from src.league.all_star import BALLOT, SLOTS
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/allstar", response_class=HTMLResponse)
def all_star_tab(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
):
    ctx = _shell_ctx(request, db, gm, league_id, "allstar", user)
    ctx.update(all_star.tab_context(db, league_id, ctx["season_id"], ctx["team_id"]))
    ctx["as_error"] = request.query_params.get("error")
    return tab_response(request, htmx, "dashboard/partials/all_star.html", ctx)


@router.post("/leagues/{league_id}/allstar/ballot")
async def save_ballot(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    """The GM's ballot: form fields <slot>_<pick>, e.g. ss_1, p_7."""
    if not gm["team_id"]:
        return HTMLResponse("You don't have a team in this league.", status_code=403)
    form = await request.form()
    raw = {
        slot: [
            form.get(f"{slot}_{pick}") or None for pick in range(1, BALLOT[slot] + 1)
        ]
        for slot in SLOTS
    }
    season_id = SeasonRepository(db).get_current_id_for_league(league_id)
    try:
        all_star.submit(db, league_id, season_id, gm["team_id"], raw)
    except ValueError as e:
        return HTMLResponse(f'<span class="as-error">✗ {e}</span>')
    db.commit()
    return HTMLResponse('<span class="as-saved">✓ Ballot saved</span>')


async def _captain_action(request, league_id, db, gm, act) -> RedirectResponse:
    """Run a captain's draft action with the form's player_id, then back to
    the tab, with the reason when it couldn't be done."""
    url = f"/leagues/{league_id}/allstar"
    if not gm["team_id"]:
        return RedirectResponse(url, status_code=303)
    form = await request.form()
    season_id = SeasonRepository(db).get_current_id_for_league(league_id)
    try:
        act(db, league_id, season_id, gm["team_id"], form.get("player_id") or "")
    except ValueError as e:
        db.rollback()
        return RedirectResponse(f"{url}?{urlencode({'error': str(e)})}", 303)
    db.commit()
    return RedirectResponse(url, status_code=303)


@router.post("/leagues/{league_id}/allstar/tie")
async def break_tie(request: Request, league_id: str, db: DB, gm: GM, _a: ActiveLeague):
    """Captain 2 picks who gets the last spot in the pool."""
    return await _captain_action(request, league_id, db, gm, all_star.break_tie)


@router.post("/leagues/{league_id}/allstar/pick")
async def draft_pick(
    request: Request, league_id: str, db: DB, gm: GM, _a: ActiveLeague
):
    """A captain's pick in the All-Star draft."""
    return await _captain_action(request, league_id, db, gm, all_star.pick)


@router.post("/leagues/{league_id}/allstar/auto")
async def auto_draft(
    request: Request, league_id: str, db: DB, gm: GM, _a: ActiveLeague
):
    """The scouts make the rest of this captain's picks."""
    return await _captain_action(request, league_id, db, gm, all_star.auto_draft)
