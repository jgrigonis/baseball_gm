# src/api/routers/lineup.py
#
# Lineup tab and saving the batting order, rotation and bullpen roles.

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

from src.api.dependencies import DB, GM, ActiveLeague, IsHTMX, User
from src.api.schemas import (
    BullpenSaveRequest,
    LineupAutofillRequest,
    LineupSaveRequest,
    RotationSaveRequest,
)
from src.api.services import coach
from src.api.services.lineup_autofill import autofill
from src.api.view_models.lineup import lineup_context
from src.db.repositories.bullpen_roles_repo import BullpenRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.lineup_preference_repo import LineupPreferenceRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.web.utils import _current_league_date, _shell_ctx, tab_response

router = APIRouter(tags=["web"])


@router.get("/leagues/{league_id}/lineup", response_class=HTMLResponse)
def lineup(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    ctx = _shell_ctx(request, db, gm, league_id, "lineup", user)

    if not gm or not gm["team_id"]:
        ctx["hitters"] = []
        ctx["pitchers"] = []
        ctx["saved_lineup"] = []
        ctx["saved_rotation"] = []
        ctx["saved_bullpen"] = []
        return tab_response(request, htmx, "dashboard/partials/lineup.html", ctx)

    ctx.update(lineup_context(db, league_id, gm, ctx.get("season_id")))
    return tab_response(request, htmx, "dashboard/partials/lineup.html", ctx)


@router.put("/leagues/{league_id}/lineup/save")
def save_lineup_prefs(
    league_id: str,
    body: LineupSaveRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    if not gm["team_id"]:
        return JSONResponse({"detail": "No team"}, status_code=400)

    lineup = [slot.model_dump() for slot in body.lineup]

    if len(lineup) > 9:
        return JSONResponse(
            {"detail": "Lineup cannot exceed 9 batters"}, status_code=422
        )
    positions_used = [s["position"] for s in lineup if s.get("position")]
    if len(positions_used) != len(set(positions_used)):
        dupes = [p for p in positions_used if positions_used.count(p) > 1]
        return JSONResponse(
            {"detail": f"Duplicate positions: {', '.join(set(dupes))}"}, status_code=422
        )

    lpr = LineupPreferenceRepository(db)
    lpr.save_preferences(gm["id"], lineup)
    coach.mark(db, league_id, "batting")

    db.commit()
    return JSONResponse({"saved": True})


@router.post("/leagues/{league_id}/lineup/autofill")
def autofill_lineup(
    league_id: str,
    body: LineupAutofillRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    """Auto-fill (keep who's there, fill the gaps) or Rebuild (start over).
    Returns the lineup for the page to show; nothing is saved."""
    if not gm or not gm["team_id"]:
        return JSONResponse({"detail": "No team"}, status_code=400)
    current = [slot.model_dump() if slot else None for slot in body.lineup]
    try:
        lineup = autofill(db, league_id, gm["team_id"], current, body.rebuild)
    except ValueError:
        return JSONResponse(
            {"detail": "Not enough healthy hitters to fill the lineup"},
            status_code=422,
        )
    return JSONResponse({"lineup": lineup})


@router.put("/leagues/{league_id}/rotation/save")
def save_rotation(
    league_id: str,
    body: RotationSaveRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    if not gm["team_id"]:
        return JSONResponse({"detail": "No team"}, status_code=400)

    rotation = body.rotation
    pointer_pid = body.pointer_pid
    season_repo = SeasonRepository(db)
    season_id = season_repo.get_most_recent_season_from_league(league_id)
    if not season_id:
        return JSONResponse({"detail": "No active season"}, status_code=400)
    team_id = gm["team_id"]

    league = LeagueRepository(db).get_by_id(league_id)
    league_state = league["state"] if league else "lobby"
    effective_date = _current_league_date(db, season_id, league_state)

    # Find where this player sits in the new rotation (1-based index)
    try:
        # .index() returns 0-4, so we add 1 for the DB's 1-5 scale
        next_order = rotation.index(pointer_pid) + 1
    except ValueError, TypeError:
        # Fallback if the pointer_pid is missing or not in the rotation
        next_order = 1

    rot_repo = TeamRotationsRepository(db, league_id)
    rot_repo.replace_rotation(
        team_id=team_id,
        season_id=season_id,
        player_ids=rotation,
        effective_date=effective_date,
        next_order=next_order,
    )
    coach.mark(db, league_id, "rotation")

    db.commit()
    return JSONResponse({"saved": True})


@router.put("/leagues/{league_id}/bullpen/save")
def save_bullpen(
    league_id: str,
    body: BullpenSaveRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    season_repo = SeasonRepository(db)
    # Resolve Season
    season_id = season_repo.get_most_recent_season_from_league(league_id)

    if not season_id:
        raise HTTPException(status_code=400, detail="No active season")

    league = LeagueRepository(db).get_by_id(league_id)
    league_state = league["state"] if league else "preseason"
    effective_date = _current_league_date(db, season_id, league_state)

    # Format assignments for the Repo
    assignments = [
        {"player_id": pid, "role": role} for pid, role in body.bullpen.items()
    ]
    bp_repo = BullpenRepository(db)
    rot_repo = TeamRotationsRepository(db, league_id)

    try:
        # Evict any bullpen-assigned pitchers who are still in the DB rotation
        bullpen_ids = {a["player_id"] for a in assignments}
        in_rotation = bp_repo.get_active_rotation_player_ids(gm["team_id"], season_id)
        for pid in bullpen_ids & in_rotation:
            rot_repo.remove_from_rotation(
                team_id=gm["team_id"],
                season_id=season_id,
                player_id=pid,
                effective_date=effective_date,
            )

        bp_repo.set_roles(
            team_id=gm["team_id"],
            season_id=season_id,
            assignments=assignments,
            effective_date=effective_date,
        )
        coach.mark(db, league_id, "bullpen")
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return JSONResponse({"saved": True})
