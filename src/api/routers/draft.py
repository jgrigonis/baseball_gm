# src/api/routers/draft.py
#
# Draft tab: the prospect board, saving draft preferences and strategy,
# previewing a strategy's picks, running the
# blitz draft, and the results page.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from src.api.dependencies import (
    DB,
    ActiveLeague,
    GM,
    GMOrViewer,
    IsHTMX,
    SinglePlayer,
    Unpaused,
    User,
)
from src.api.schemas import DraftPreferencesRequest, DraftStrategyRequest
from src.api.services import coach
from src.api.services.draft_execute import execute_blitz_draft
from src.api.services.draft_preview import preview_picks
from src.api.view_models.draft import draft_rounds
from src.api.view_models.player_cards import draft_roster_card, prospect_card
from src.db.locks import league_lock
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.season_repo import SeasonRepository
from src.league.offseason.draft_strategy import CHIPS, DraftStrategy
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


# ── Draft actions ──────────────────────────────────────────────────────────────


@router.put("/leagues/{league_id}/draft/preferences")
def save_draft_preferences(
    league_id: str,
    body: DraftPreferencesRequest,
    db: DB,
    user: User,
    gm: GM,
    _active: ActiveLeague,
    # gm_session: str | None = Cookie(default=None),
):
    """
    Save the GM's draft preference list. Called from JS using the session
    cookie — no token exposure needed. Proxies to the existing draft logic.
    """

    draft_repo = DraftRepository(db)

    draft = draft_repo.get_current_for_league(league_id)
    if not draft:
        return JSONResponse({"detail": "No draft found"}, status_code=404)
    if draft["state"] == "complete":
        return JSONResponse({"detail": "Draft is already complete"}, status_code=409)

    player_ids = body.player_ids
    if not player_ids:
        return JSONResponse({"detail": "player_ids required"}, status_code=422)

    missing = draft_repo.validate_player_ids(player_ids)
    if missing:
        return JSONResponse({"detail": f"Unknown player: {missing}"}, status_code=422)

    draft_repo.save_preferences(draft["id"], gm["id"], player_ids)
    coach.mark(db, league_id, "prefs")
    db.commit()

    return JSONResponse({"saved": len(player_ids)})


def _strategy_or_error(
    draft_repo: DraftRepository, league_id: str, body: DraftStrategyRequest
) -> DraftStrategy | JSONResponse:
    """The request as a DraftStrategy, or a 422 saying what's wrong with it."""
    try:
        strategy = DraftStrategy(
            chips=body.chips,
            age_pref=body.age_pref,
            pins=list(dict.fromkeys(body.pins)),
        )
    except ValueError as e:
        return JSONResponse({"detail": str(e)}, status_code=422)

    prospect_ids = {p["id"] for p in draft_repo.get_prospects(league_id)}
    missing = next((pid for pid in strategy.pins if pid not in prospect_ids), None)
    if missing:
        return JSONResponse({"detail": f"Unknown prospect: {missing}"}, status_code=422)
    return strategy


@router.put("/leagues/{league_id}/draft/strategy")
def save_draft_strategy(
    league_id: str,
    body: DraftStrategyRequest,
    db: DB,
    user: User,
    gm: GM,
    _active: ActiveLeague,
):
    """Save the GM's draft strategy: need chips, age preference and pins.
    It replaces any ranked list from the Advanced board, which the draft
    would otherwise use first."""
    draft_repo = DraftRepository(db)

    draft = draft_repo.get_current_for_league(league_id)
    if not draft:
        return JSONResponse({"detail": "No draft found"}, status_code=404)
    if draft["state"] == "complete":
        return JSONResponse({"detail": "Draft is already complete"}, status_code=409)

    strategy = _strategy_or_error(draft_repo, league_id, body)
    if isinstance(strategy, JSONResponse):
        return strategy

    draft_repo.save_strategy(draft["id"], gm["id"], strategy)
    draft_repo.clear_preferences(draft["id"], gm["id"])
    coach.mark(db, league_id, "prefs")
    db.commit()

    return JSONResponse({"saved": True})


@router.post("/leagues/{league_id}/draft/preview")
def preview_draft_strategy(
    league_id: str,
    body: DraftStrategyRequest,
    db: DB,
    user: User,
    gm: GM,
    _active: ActiveLeague,
):
    """The GM's first few projected picks with the strategy in the body,
    which doesn't need to be saved, and which pins go to other teams first."""
    draft_repo = DraftRepository(db)

    draft = draft_repo.get_current_for_league(league_id)
    if not draft or draft["state"] == "complete" or not gm["team_id"]:
        return JSONResponse({"picks": [], "pins_gone": {}})

    strategy = _strategy_or_error(draft_repo, league_id, body)
    if isinstance(strategy, JSONResponse):
        return strategy

    return JSONResponse(
        preview_picks(db, league_id, draft["id"], gm["team_id"], strategy)
    )


# ── Tab: Draft ─────────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/draft", response_class=HTMLResponse)
def draft_tab(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    draft_repo = DraftRepository(db)
    draft = draft_repo.get_current_for_league(league_id)
    if draft and draft["state"] == "complete":
        return RedirectResponse(f"/leagues/{league_id}/draft/results", status_code=302)

    ctx = _shell_ctx(request, db, gm, league_id, "draft", user)
    player_repo = PlayerRepository(db)

    if draft:
        picked_ids = draft_repo.get_picked_ids(draft["id"])
        all_players = draft_repo.get_prospects(league_id)

        board = []
        for row in all_players:
            if row["id"] in picked_ids:
                continue
            board.append(prospect_card(row, player_repo.get_player_skills(row["id"])))

        prefs = draft_repo.get_preferences(draft["id"], gm["id"]) if gm else []
        strategy = draft_repo.get_strategy(draft["id"], gm["id"])

        pick_position = None
        if gm["team_id"]:
            pick_position = draft_repo.get_pick_position(draft["id"], gm["team_id"])

        ctx["draft_id"] = draft["id"]
        ctx["board"] = board
        ctx["preferences"] = prefs
        ctx["strategy"] = vars(strategy) if strategy else None
        ctx["pick_position"] = pick_position
    else:
        ctx["draft_id"] = None
        ctx["board"] = []
        ctx["preferences"] = []
        ctx["strategy"] = None
        ctx["pick_position"] = None
    ctx["chips"] = [
        {
            "key": c.key,
            "label": c.label,
            "kind": "position" if c.group == c.key else "type",
        }
        for c in CHIPS.values()
    ]

    # Load GM's current roster for the right-hand column
    players = []
    if gm["team_id"]:
        roster_rows = player_repo.get_team_roster_with_skills(gm["team_id"])
        for row in roster_rows:
            skills = player_repo.get_player_skills(row["id"])
            players.append(draft_roster_card(row, skills))
    ctx["players"] = players

    return tab_response(request, htmx, "dashboard/partials/draft.html", ctx)


@router.post("/leagues/{league_id}/draft/execute")
def execute_draft(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _: SinglePlayer,
    _unpaused: Unpaused,
):
    """Execute the blitz auto-draft and redirect to results."""
    with league_lock(db, league_id):
        draft = DraftRepository(db).get_current_for_league(league_id)

        if not draft:
            return RedirectResponse(f"/leagues/{league_id}/draft", status_code=302)

        # If already complete, just go to results
        if draft["state"] == "complete":
            return RedirectResponse(
                f"/leagues/{league_id}/draft/results", status_code=302
            )

        execute_blitz_draft(draft["id"], db)
        db.commit()
    return RedirectResponse(f"/leagues/{league_id}/draft/results", status_code=302)


@router.get("/leagues/{league_id}/draft/results", response_class=HTMLResponse)
def draft_results(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
    season_id: str | None = None,
):
    """Show completed draft results — all picks by round, your picks highlighted.
    `season_id` (from the History tab) shows the draft held before that season."""
    ctx = _shell_ctx(request, db, gm, league_id, "draft", user)

    draft_repo = DraftRepository(db)
    season = (
        SeasonRepository(db).get_for_league(league_id, season_id) if season_id else None
    )
    if season:
        draft = draft_repo.get_for_season(league_id, season["id"])
    else:
        draft = draft_repo.get_current_for_league(league_id)

    rounds = draft_rounds(db, league_id, draft["id"], gm["team_id"]) if draft else []

    ctx["rounds"] = rounds
    ctx["draft_done"] = bool(draft and draft["state"] == "complete")
    ctx["draft_year"] = season["year"] if season else None
    return tab_response(request, htmx, "dashboard/partials/draft_results.html", ctx)
