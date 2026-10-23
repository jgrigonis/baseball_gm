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

from src.api.dependencies import DB, GM, Commissioner, User
from src.api.services.league_start import start_league
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.league_repo import LeagueRepository
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
    rows = gm_repo.get_users_leagues(user["id"])

    return templates.TemplateResponse(
        request,
        "leagues/index.html",
        {
            "user": user,
            "leagues": [dict(r) for r in rows],
        },
    )


@router.get("/leagues/new", response_class=HTMLResponse)
def new_league_page(request: Request):
    return templates.TemplateResponse(request, "leagues/new.html", {})


# was create_league
@router.post("/leagues/new")
def new_league(
    db: DB,
    user: User,
    name: str = Form(...),
    mode: str = Form("blitz"),
    decision_window_sec: int = Form(120),
    draft_window_sec: int = Form(300),
    reentry_enabled: bool = Form(True),
):
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
            "reentry_enabled": reentry_enabled,
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
    league = league_repo.get_by_join_code(join_code.upper())
    if not league:
        return templates.TemplateResponse(
            request, "leagues/join.html", {"error": "League not found."}
        )
    if league["state"] != "lobby":
        return templates.TemplateResponse(
            request, "leagues/join.html", {"error": "League has already started."}
        )

    # 2. Check for existing membership via repo
    existing_gm = gm_repo.get_by_user_and_league(user["id"], league["id"])
    if existing_gm:
        return RedirectResponse(f"/leagues/{league['id']}/", status_code=302)

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
    start_league(league_id, db)
    db.commit()
    return RedirectResponse(f"/leagues/{league_id}/", status_code=302)


# ── League rename ──────────────────────────────────────────────────────────────


class RenameLeagueRequest(BaseModel):
    name: str


@router.post("/leagues/{league_id}/rename")
def rename_league(
    league_id: str,
    body: RenameLeagueRequest,
    db: DB,
    gm: GM,
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

    gms_in_league = gm_repo.get_all_in_league(league_id)
    # This boolean is what the Jinja template is looking for
    is_commish = league["commissioner_gm_id"] == gm["id"]

    context_drawer = {
        "league_id": league_id,
        "league_name": league["name"],
        "is_commissioner": bool(is_commish),
        "gms": list(gms_in_league),
        "num_teams": league["num_teams"],
        "league_num_teams": league["num_teams"],  # Dual-mapping for safety
        "league_mode": league["mode"],
        "join_code": league.get("join_code"),
        "league_decision_window_sec": league["decision_window_sec"],
        "league_draft_window_sec": league["draft_window_sec"],
        "league_pace_control": league.get("pace_control", "manual"),
        "current_gm_id": str(gm["id"]),
    }

    return templates.TemplateResponse(
        request=request, name="dashboard/lobby.html", context=context_drawer
    )
