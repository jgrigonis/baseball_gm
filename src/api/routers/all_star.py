# src/api/routers/all_star.py
#
# The All-Star tab: the ballot while voting is open, the All-Stars and the
# captains' draft after, then the Home Run Derby, the All-Star Game and the
# Rookie Game (src/api/services/all_star.py, hr_derby.py, rookie_game.py).

from __future__ import annotations

import html
from functools import partial
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.api.dependencies import DB, GM, ActiveLeague, GMOrViewer, IsHTMX, User
from src.api.services import all_star, coach, hr_derby, rookie_game
from src.db.repositories.all_star_repo import AllStarRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.league.all_star import BALLOT, SLOTS
from src.web.utils import _shell_ctx, tab_response, templates

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
    if ctx["as_phase"] in ("done", "played"):
        ctx.update(hr_derby.tab_context(db, league_id, ctx["season_id"]))
        ctx.update(
            rookie_game.tab_context(db, league_id, ctx["season_id"], ctx["team_id"])
        )
    ctx["as_error"] = request.query_params.get("error")
    ctx.update(_weekend_context(request, db, league_id, ctx))
    # In a tutorial league, seeing the All-Stars or the break's results
    # finishes a coach step.
    if ctx.get("coach"):
        league = LeagueRepository(db).get_by_id(league_id)
        pick_due = bool(ctx.get("all_star_pick_due"))
        if coach.mark_all_star_visit(db, league, ctx["as_phase"], pick_due):
            ctx["coach"] = coach.coach_ctx(db, league)
    return tab_response(request, htmx, "dashboard/partials/all_star.html", ctx)


@router.get(
    "/leagues/{league_id}/allstar/box/{event}/{season_id}", response_class=HTMLResponse
)
def all_star_box(
    request: Request,
    league_id: str,
    event: str,
    season_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
):
    """A played All-Star Game's (or, with event "rookie", Rookie Game's) line
    score, MVP and box score, for the game panel (openAllStarBox in
    shell.html): from the season summary, the news, a player's career page or
    the weekend results card, for any season of the league."""
    if event not in ("all_star", rookie_game.EVENT):
        return HTMLResponse("Game not found", status_code=404)
    season = SeasonRepository(db).get_for_league(league_id, season_id)
    g = AllStarRepository(db, event).game(season_id) if season else None
    if not g or g["state"] != "played":
        return HTMLResponse("Game not found", status_code=404)
    ctx = _shell_ctx(request, db, gm, league_id, user=user)
    x = all_star.game_context(db, league_id, season_id, ctx["team_id"], g, [], event)
    ctx.update({"x": x, "box_year": season["year"]})
    return templates.TemplateResponse(
        request=request, name="dashboard/partials/_all_star_box.html", context=ctx
    )


def _weekend_context(request: Request, db, league_id: str, ctx: dict) -> dict:
    """The All-Star weekend card at the top of the tab: before the weekend,
    a Sim All-Star Weekend button once the captains' picks are in (a GM in a
    single-player league; a multiplayer league plays it when the league
    moves on); after it, when the sim has just played it (?weekend=1), what
    happened, with links down to each event."""
    if ctx["as_phase"] == "played":
        return {"weekend_just_played": request.query_params.get("weekend") == "1"}
    if ctx["as_phase"] != "done" or ctx.get("league_state") != "season":
        return {}
    return {
        "weekend_due": True,
        "weekend_can_sim": bool(
            ctx.get("team_id")
            and not ctx.get("is_viewer")
            and not ctx.get("multiplayer")
        ),
        "weekend_picks_left": all_star.person_drafting(db, league_id, ctx["season_id"]),
    }


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
        msg = html.escape(f"✗ {e}")
        return HTMLResponse(
            f'<span class="as-error" hidden data-toast="{msg}" data-toast-kind="err"></span>'
        )
    coach.mark(db, league_id, "allstar_vote")
    db.commit()
    # Shown as a toast (gmToast in dialogs.js); .as-saved tells the page it worked.
    return HTMLResponse(
        '<span class="as-saved" hidden data-toast="✓ Ballot saved" data-toast-kind="ok"></span>'
    )


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


@router.post("/leagues/{league_id}/allstar/rookie/pick")
async def rookie_pick(
    request: Request, league_id: str, db: DB, gm: GM, _a: ActiveLeague
):
    """A captain's pick in the Rookie Game draft."""
    act = partial(all_star.pick, event=rookie_game.EVENT)
    return await _captain_action(request, league_id, db, gm, act)


@router.post("/leagues/{league_id}/allstar/rookie/auto")
async def rookie_auto_draft(
    request: Request, league_id: str, db: DB, gm: GM, _a: ActiveLeague
):
    """The scouts make the rest of this captain's Rookie Game picks."""
    act = partial(all_star.auto_draft, event=rookie_game.EVENT)
    return await _captain_action(request, league_id, db, gm, act)
