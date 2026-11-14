# src/api/routers/draft.py
#
# Draft tab: the prospect board, saving a draft strategy,
# previewing a strategy's picks, running the
# blitz draft, and the results page.

from __future__ import annotations

from datetime import UTC, date, datetime

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
from src.api.schemas import DraftPickRequest, DraftScoutsRequest, DraftStrategyRequest
from src.api.services import coach, live_draft, sim_jobs, team_states
from src.api.services.draft_needs import needs_for_draft
from src.api.services.draft_preview import preview_picks
from src.api.view_models.draft import draft_rounds, last_season
from src.api.view_models.player_cards import prospect_card
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.season_repo import SeasonRepository
from src.league import team_state
from src.league.offseason.draft_strategy import CHIPS, DraftStrategy
from src.web.utils import _shell_ctx, tab_response

router = APIRouter(tags=["web"])


# ── Draft actions ──────────────────────────────────────────────────────────────


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
    """Save the GM's draft strategy: need chips, age preference and pins."""
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

    ctx["live"] = None
    if live_draft.is_live(draft):
        live = live_draft.LiveDraft(db, draft["id"])
        ctx["live"] = {
            "state": draft["state"],
            "timer": live.state(gm["team_id"])["timer"],
        }
    if draft:
        picked_ids = draft_repo.get_picked_ids(draft["id"])
        all_players = draft_repo.get_prospects(league_id)

        board = []
        for row in all_players:
            if row["id"] in picked_ids:
                continue
            board.append(prospect_card(row, player_repo.get_player_skills(row["id"])))

        strategy = draft_repo.get_strategy(draft["id"], gm["id"])

        pick_position = None
        if gm["team_id"]:
            pick_position = draft_repo.get_pick_position(draft["id"], gm["team_id"])

        ctx["draft_id"] = draft["id"]
        ctx["board"] = board
        ctx["strategy"] = vars(strategy) if strategy else None
        needs = (
            needs_for_draft(db, draft["id"]).get(gm["team_id"])
            if gm["team_id"]
            else None
        )
        ctx["suggested"] = (
            {"chips": needs.chips, "reasons": needs.reasons}
            if needs
            else {"chips": {}, "reasons": {}}
        )
        ctx["pick_position"] = pick_position
        # The front office's read on the GM's team, as on the standings page,
        # for the season the AI teams draft by.
        state = (
            team_states.states(
                db, league_id, draft["season_id"], date.today().isoformat()
            ).get(gm["team_id"])
            if gm["team_id"] and draft["season_id"]
            else None
        )
        ctx["my_state"] = team_state.describe(state) if state else ""
        ctx["last_season"] = (
            last_season(db, league_id, gm["team_id"], draft["season_id"])
            if gm["team_id"]
            else None
        )
    else:
        ctx["draft_id"] = None
        ctx["board"] = []
        ctx["strategy"] = None
        ctx["suggested"] = {"chips": {}, "reasons": {}}
        ctx["pick_position"] = None
        ctx["my_state"] = ""
        ctx["last_season"] = None
    ctx["chips"] = [
        {
            "key": c.key,
            "label": c.label,
            "kind": "position" if c.group == c.key else "type",
        }
        for c in CHIPS.values()
    ]

    return tab_response(request, htmx, "dashboard/partials/draft.html", ctx)


# ── Live draft (Long Form) ──────────────────────────────────────────────────────


def _live_or_error(db, league_id: str, lock: bool = True):
    live = live_draft.for_league(db, league_id, lock=lock)
    if not live:
        return JSONResponse({"detail": "There's no live draft on."}, status_code=409)
    return live


@router.post("/leagues/{league_id}/draft/start")
def start_live_draft(
    league_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _: SinglePlayer,
    _unpaused: Unpaused,
):
    """A one-person league starts its live draft: the AI teams pick up to
    the person's first pick. (A multiplayer league starts it when everyone
    is ready.)"""
    live = _live_or_error(db, league_id)
    if isinstance(live, JSONResponse):
        return live
    try:
        live.start()
    except ValueError as e:
        db.rollback()
        return JSONResponse({"detail": str(e)}, status_code=409)
    db.commit()
    return JSONResponse({"started": True})


@router.get("/leagues/{league_id}/draft/live")
def live_draft_state(league_id: str, db: DB, gm: GM):
    """The draft room's poll: the pick on the clock, its clock and the latest
    picks. A clock that has run out is settled first, and a draft whose
    picks are all in is sent to the sim worker to finish, if it isn't yet."""
    draft = DraftRepository(db).get_current_for_league(league_id)
    if draft and draft["state"] == "complete":
        return JSONResponse(
            {"done": True, "redirect": f"/leagues/{league_id}/draft/results"}
        )
    live = live_draft.for_league(db, league_id)
    if not live:
        return JSONResponse({"detail": "There's no live draft on."}, status_code=409)
    deadline = live.draft.get("pick_deadline")
    if deadline is not None and deadline <= datetime.now(UTC):
        live = live_draft.LiveDraft(db, live.id, lock=True)
        live.expire()
        db.commit()
    if live.done and not sim_jobs.league_has_job(db, league_id):
        live._picks_done()
        db.commit()
    return JSONResponse(
        {**live.state(gm["team_id"]), "simming": sim_jobs.league_has_job(db, league_id)}
    )


@router.get("/leagues/{league_id}/draft/live/list")
def live_draft_list(league_id: str, db: DB, gm: GM):
    """The GM's next pick: the default pick and the best players likely
    still there."""
    live = live_draft.for_league(db, league_id)
    if not live or not gm["team_id"] or live.draft["state"] != "open":
        return JSONResponse({"next": None})
    return JSONResponse({"next": live.short_list(gm["team_id"])})


@router.post("/leagues/{league_id}/draft/pick")
def live_draft_pick(
    league_id: str,
    body: DraftPickRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _unpaused: Unpaused,
):
    """The GM's pick, when they're on the clock. The AI picks after it are
    made straight away."""
    live = _live_or_error(db, league_id)
    if isinstance(live, JSONResponse):
        return live
    try:
        live.pick(gm["team_id"], body.player_id)
    except ValueError as e:
        db.rollback()
        return JSONResponse({"detail": str(e)}, status_code=409)
    db.commit()
    return JSONResponse({"picked": True})


@router.post("/leagues/{league_id}/draft/scouts")
def live_draft_scouts(
    league_id: str,
    body: DraftScoutsRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    _unpaused: Unpaused,
):
    """The scouts make the GM's pick (the default), or with rest every pick
    they have left."""
    live = _live_or_error(db, league_id)
    if isinstance(live, JSONResponse):
        return live
    slot = live.current()
    if not body.rest and (not slot or slot.team_id != gm["team_id"]):
        db.rollback()
        return JSONResponse({"detail": "It isn't your pick."}, status_code=409)
    live.scouts_pick(gm["team_id"], rest=body.rest)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/leagues/{league_id}/draft/take-over")
def live_draft_take_over(
    league_id: str, db: DB, gm: GM, _active: ActiveLeague, _unpaused: Unpaused
):
    """The GM takes their picks back from the scouts."""
    live = _live_or_error(db, league_id)
    if isinstance(live, JSONResponse):
        return live
    live.take_over(gm["team_id"])
    db.commit()
    return JSONResponse({"ok": True})


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
    """Queue the blitz auto-draft for the sim worker. The page polls the job,
    then goes to the results."""
    if live_draft.is_live(DraftRepository(db).get_current_for_league(league_id)):
        return JSONResponse(
            {"detail": "This is a live draft: start it and make your picks."},
            status_code=409,
        )
    job_id = sim_jobs.submit(db, league_id, "draft", gm_id=gm["id"])
    return JSONResponse(
        {"job_id": job_id, "poll": f"/leagues/{league_id}/jobs/{job_id}"},
        status_code=202,
    )


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
