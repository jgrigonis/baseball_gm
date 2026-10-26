# src/api/routers/leagues.py
#
# League list, creating and joining leagues, starting a league, renaming it,
# and the lobby page that /leagues/{id}/ shows before the league starts.

from __future__ import annotations

import random
import string
import uuid

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from src.api.dependencies import DB, GM, ActiveLeague, Commissioner, User
from src.api.services.leave_league import leave_league
from src.api.services.league_start import start_league
from src.db.locks import league_lock
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.league_repo import LeagueRepository
from src.league.league_modes import BLITZ, DEFAULT_MODE, SPEED_BLITZ, get_mode
from src.web.utils import templates

router = APIRouter(tags=["web"])


# ── League list ────────────────────────────────────────────────────────────────


@router.get("/leagues/", response_class=HTMLResponse)
def leagues_index(
    request: Request,
    db: DB,
    user: User,
):
    # Guests from before passwords existed choose a login before going on.
    if not user["has_password"]:
        return RedirectResponse("/auth/set-password", status_code=302)

    gm_repo = GMRepository(db)
    # Fetch User's Leagues
    leagues = [dict(r) for r in gm_repo.get_users_leagues(user["id"])]
    for league in leagues:
        league["state_label"] = state_label(league["state"], league["season_number"])

    return templates.TemplateResponse(
        request,
        "leagues/index.html",
        {
            "user": user,
            "leagues": leagues,
        },
    )


def state_label(state: str, season_number: int) -> str:
    """The league's phase and which season it's in, e.g. "Draft 1" or
    "Playoffs 3". The lobby and a finished league have no season number."""
    if state in ("lobby", "complete") or not season_number:
        return state.title()
    return f"{state.title()} {season_number}"


@router.get("/leagues/new", response_class=HTMLResponse)
def new_league_page(request: Request):
    return templates.TemplateResponse(
        request,
        "leagues/new.html",
        {"default_mode": DEFAULT_MODE, "modes": [BLITZ, SPEED_BLITZ]},
    )


# was create_league
@router.post("/leagues/new")
def new_league(
    db: DB,
    user: User,
    name: str = Form(...),
    mode: str = Form(DEFAULT_MODE),
    decision_window_sec: int = Form(120),
    draft_window_sec: int = Form(300),
    lineup_window_sec: int = Form(600),
    reentry_enabled: bool = Form(True),
    pace_control: str = Form("timer"),
    sim_period_days: int = Form(3),
    num_seasons: int = Form(10),
):
    get_mode(mode)  # rejects an unknown mode
    if pace_control not in ("timer", "confirmed"):
        raise ValueError(f"Unknown pace '{pace_control}'.")
    if not 1 <= sim_period_days <= 30:
        raise ValueError("Days per sim period must be between 1 and 30.")
    if not 1 <= num_seasons <= 420:
        raise ValueError("Number of seasons must be between 1 and 420.")

    league_id = str(uuid.uuid4())
    # gm_id = str(uuid.uuid4())
    join_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    league_repo = LeagueRepository(db)
    gm_repo = GMRepository(db)

    # 1. Create the League
    league_repo.create_new_league(
        league_id=league_id,
        name=name,
        join_code=join_code,
        mode=mode,
        commissioner_gm_id=None,
        settings={
            "decision_window_sec": decision_window_sec,
            "draft_window_sec": draft_window_sec,
            "lineup_window_sec": lineup_window_sec,
            "reentry_enabled": reentry_enabled,
            "pace_control": pace_control,
            "sim_period_days": sim_period_days,
            "num_seasons": num_seasons,
        },
    )
    # 2. GM setup

    gm_id = gm_repo.create_gm(
        league_id=league_id,
        user_id=user["id"],
        display_name=user["display_name"],
    )
    # 3. Update the League (Now the GM exists, so the commish ID is valid)
    gm_repo.set_commissioner(gm_id=gm_id, league_id=league_id)

    db.commit()
    return RedirectResponse(f"/leagues/{league_id}/", status_code=302)


@router.post("/leagues/join")
def join_league(
    request: Request,
    db: DB,
    user: User,
    join_code: str = Form(...),
):
    league_repo = LeagueRepository(db)
    gm_repo = GMRepository(db)

    # 1. Use repo to find the league
    join_code = join_code.strip().upper()
    league = league_repo.get_by_join_code(join_code)
    if not league:
        return templates.TemplateResponse(
            request,
            "leagues/join.html",
            {"error": "No league found with that join code.", "join_code": join_code},
        )

    # 2. A GM already in the league goes straight to it, started or not
    existing_gm = gm_repo.get_by_user_and_league(user["id"], league["id"])
    if existing_gm:
        return RedirectResponse(f"/leagues/{league['id']}/", status_code=302)

    if league["state"] != "lobby":
        return templates.TemplateResponse(
            request,
            "leagues/join.html",
            {
                "error": f"{league['name']} has already started, so it can't take new GMs.",
                "join_code": join_code,
            },
        )

    # 3. Join the league using our clean GM creator
    gm_repo.create_gm(
        league_id=league["id"],
        user_id=user["id"],
        display_name=user["display_name"],
    )
    db.commit()

    return RedirectResponse(f"/leagues/{league['id']}/", status_code=302)


@router.get("/leagues/join", response_class=HTMLResponse)
def join_page(request: Request):
    return templates.TemplateResponse(request, "leagues/join.html", {})


# ── League actions ────────────────────────────────────────────────────────────


@router.post("/leagues/{league_id}/start")
def start_league_router(
    league_id: str,
    db: DB,
    _: Commissioner,
):
    with league_lock(db, league_id):
        start_league(league_id, db)
        db.commit()
    return RedirectResponse(f"/leagues/{league_id}/", status_code=302)


@router.post("/leagues/{league_id}/leave")
def leave_league_router(
    league_id: str,
    db: DB,
    gm: GM,
):
    """Leave the league. Once it has started, AI takes over the GM's team."""
    leave_league(db, league_id, gm["id"])
    return JSONResponse({"left": True})


# ── League rename ──────────────────────────────────────────────────────────────


class RenameLeagueRequest(BaseModel):
    name: str


@router.post("/leagues/{league_id}/rename")
def rename_league(
    league_id: str,
    body: RenameLeagueRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    name = body.name.strip()
    if not name:
        return JSONResponse({"detail": "Name required"}, status_code=422)
    league_repo = LeagueRepository(db)
    league = league_repo.get_by_id(league_id)
    if not league or league["commissioner_gm_id"] != gm["id"]:
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    league_repo.rename(league_id, name)
    db.commit()
    return JSONResponse({"name": name})


# ── Dashboard shell ────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    gm_repo = GMRepository(db)
    league_repo = LeagueRepository(db)
    league = league_repo.get_by_id(league_id)
    if not league:
        return RedirectResponse("/leagues/")

    is_commish = league["commissioner_gm_id"] == gm["id"]

    state = league["state"]
    # Redirect logic
    if state in ("preseason", "draft"):
        return RedirectResponse(f"/leagues/{league_id}/draft")
    if state in ("season", "playoffs"):
        return RedirectResponse(f"/leagues/{league_id}/standings")
    if state == "evaluation":
        # Simplified the season fetch for now to get you back to green
        return RedirectResponse(f"/leagues/{league_id}/history/1/")
    if state == "complete":
        return RedirectResponse(f"/leagues/{league_id}/history")

    context = _lobby_gms_context(gm_repo, league, gm)
    context.update(
        {
            "league_name": league["name"],
            "is_commissioner": bool(is_commish),
            "league_num_teams": league["num_teams"],  # Dual-mapping for safety
            "league_mode": get_mode(league["mode"]),
            "league_decision_window_sec": league["decision_window_sec"],
            "league_draft_window_sec": league["draft_window_sec"],
            "league_lineup_window_sec": league["lineup_window_sec"],
            "league_reentry_enabled": bool(league["reentry_enabled"]),
            "league_pace_control": league["pace_control"],
            "league_sim_period_days": league["sim_period_days"],
            "league_num_seasons": league["num_seasons"],
        }
    )

    return templates.TemplateResponse(
        request=request, name="dashboard/lobby.html", context=context
    )


def _lobby_gms_context(gm_repo: GMRepository, league, gm) -> dict:
    # Every team without a human GM gets an AI one when the league starts, so
    # the lobby shows those open slots as AI GMs. Each GM who joins takes one.
    gms = list(gm_repo.get_all_in_league(league["id"]))
    return {
        "league_id": league["id"],
        "league_state": league["state"],
        "gms": gms,
        "ai_slots": max(league["num_teams"] - len(gms), 0),
        "num_teams": league["num_teams"],
        "join_code": league.get("join_code"),
        "current_gm_id": str(gm["id"]),
    }


@router.get("/leagues/{league_id}/lobby/gms", response_class=HTMLResponse)
def lobby_gms(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
):
    """The lobby's GM list, polled while GMs wait for the league to start.

    Once the league has started, HX-Redirect sends the page to the dashboard,
    which redirects on to wherever the league is now.
    """
    league = LeagueRepository(db).get_by_id(league_id)
    if not league or league["state"] != "lobby":
        return HTMLResponse("", headers={"HX-Redirect": f"/leagues/{league_id}/"})
    return templates.TemplateResponse(
        request,
        "dashboard/partials/_lobby_gms.html",
        _lobby_gms_context(GMRepository(db), league, gm),
    )
