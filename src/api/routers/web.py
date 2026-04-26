# src/api/routers/web.py
#
# HTML-rendering routes for the production web UI.
#
# Identity model (matches schema.py):
#   users.session_token  ← stored in "gm_session" browser cookie
#   users → gms          via gms.user_id (one gm row per league)
#
# So the resolution chain is:
#   cookie → users row → gms row WHERE league_id = ?
#
# Guest creation only makes a users row. The gms row is created
# by the existing leagues.py router when the user creates/joins a league.

from __future__ import annotations

import asyncio
import json
import logging
import random
import string
import uuid
import traceback
from datetime import date

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Form, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.api.dependencies import DB, User, OptionalUser, GM, Commissioner, IsHTMX
from src.api.schemas import player_row_to_grades, skill_to_grade, BullpenSaveRequest
from src.api.services.draft_execute import execute_blitz_draft
from src.api.services.league_start import start_league
from src.api.services.offseason_service import run_offseason
from src.api.services.sim_next import sim_next_day
from src.api.services.sim_playoff import sim_playoff
from src.db.repositories.bullpen_roles_repo import BullpenRepository
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.gm_evaluation_repo import GMEvaluationRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.lineup_preference_repo import LineupPreferenceRepository
from src.db.repositories.pitcher_state import PitcherStateRepository
from src.db.repositories.player_energy import PlayerEnergyRepository
from src.db.repositories.player_games import PlayerGameRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.playoff_repo import PlayoffRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.series_repo import SeriesRepository
from src.db.repositories.standings_repo import StandingsRepository
from src.db.repositories.team_game_repo import TeamGameRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.db.repositories.user_repo import UserRepository
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_skills import PlayerSkills
from src.web.utils import tab_response, _shell_ctx, _current_league_date

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="src/web/templates")


# ── Player rating helpers ─────────────────────────────────────────────────────


def _compute_ratings(skills: dict, throws: str) -> dict:
    """
    Run PlayerEvaluator on a raw skills dict.
    Returns the full ratings map plus derived composites:
      if_rating   = max(2b, 3b, ss)
      of_rating   = max(lf, cf, rf)
      best_def    = max(if, of, c, 1b)
      best_def_label = "IF" | "OF" | "CA" | "1B"
    """
    try:
        ps = PlayerSkills(skills)
        ratings = PlayerEvaluator.rate_player(ps, throws or "R")
    except Exception:
        logger.exception(
            "Failed to evaluate player skills: skills=%s throws=%s", skills, throws
        )
        return {}

    if_rating = max(ratings.get("2b", 0), ratings.get("3b", 0), ratings.get("ss", 0))
    of_rating = max(ratings.get("lf", 0), ratings.get("cf", 0), ratings.get("rf", 0))
    groups = {
        "IF": if_rating,
        "OF": of_rating,
        "CA": ratings.get("c", 0),
        "1B": ratings.get("1b", 0),
    }

    best_def_label = max(groups, key=groups.get)
    best_def = groups[best_def_label]

    ratings["if"] = if_rating
    ratings["of"] = of_rating
    ratings["best_def"] = best_def
    ratings["best_def_label"] = best_def_label
    return ratings


def _ratings_to_grade_map(grades, skills: dict, ratings: dict) -> list:
    """
    Build the section-based grade_map for the player detail panel.
    Pitchers:  Pitching / General / Defense / Hitting
    Hitters:   Hitting  / General / Defense / Pitching
    Ratings-based entries use skill_to_grade(rating_value).
    """
    g = skill_to_grade  # shorthand

    def rg(key: str) -> str:
        return g(ratings.get(key))

    pitching_section = {
        "section": "Pitching",
        "skills": [
            {
                "key": "strikes",
                "label": "Stuff",
                "grade": grades.stuff or g(skills.get("strikes")),
            },
            {
                "key": "accuracy",
                "label": "Control",
                "grade": grades.control or g(skills.get("accuracy")),
            },
            {
                "key": "stamina",
                "label": "Stamina",
                "grade": grades.stamina or g(skills.get("stamina")),
            },
            {
                "key": "recovery",
                "label": "Recovery",
                "grade": grades.recovery or g(skills.get("recovery")),
            },
            {
                "key": "ground_balls",
                "label": "GB tendency",
                "grade": g(skills.get("ground_balls")),
            },
            {"key": "sp", "label": "SP rating", "grade": rg("sp")},
            {"key": "rp", "label": "RP rating", "grade": rg("rp")},
        ],
    }

    hitting_section = {
        "section": "Hitting",
        "skills": [
            {
                "key": "contact",
                "label": "Contact",
                "grade": grades.contact or g(skills.get("contact")),
            },
            {
                "key": "power",
                "label": "Power",
                "grade": grades.power or g(skills.get("power")),
            },
            {"key": "eye", "label": "Eye", "grade": grades.eye or g(skills.get("eye"))},
            {
                "key": "speed",
                "label": "Speed",
                "grade": grades.speed or g(skills.get("speed")),
            },
            {
                "key": "base_running",
                "label": "Baserunning",
                "grade": g(skills.get("base_running")),
            },
            {"key": "bunting", "label": "Bunting", "grade": g(skills.get("bunting"))},
            {"key": "lead_off", "label": "Leadoff", "grade": rg("lead_off")},
            {
                "key": "power_hitter",
                "label": "Power hitter",
                "grade": rg("power_hitter"),
            },
            {
                "key": "contact_hitter",
                "label": "Contact hitter",
                "grade": rg("contact_hitter"),
            },
        ],
    }

    defense_section = {
        "section": "Defense",
        "skills": [
            {"key": "c", "label": "Catcher", "grade": rg("c")},
            {"key": "1b", "label": "First Base", "grade": rg("1b")},
            {"key": "2b", "label": "Second Base", "grade": rg("2b")},
            {"key": "3b", "label": "Third Base", "grade": rg("3b")},
            {"key": "ss", "label": "Shortstop", "grade": rg("ss")},
            {"key": "lf", "label": "Left Field", "grade": rg("lf")},
            {"key": "cf", "label": "Center Field", "grade": rg("cf")},
            {"key": "rf", "label": "Right Field", "grade": rg("rf")},
            {"key": "arm", "label": "Arm", "grade": grades.arm or g(skills.get("arm"))},
        ],
    }

    general_section = {
        "section": "General",
        "skills": [
            {"key": "clutch", "label": "Clutch", "grade": g(skills.get("clutch"))},
            {
                "key": "durability",
                "label": "Durability",
                "grade": g(skills.get("durability")),
            },
            {
                "key": "overall_offense",
                "label": "Off. rating",
                "grade": rg("overall_offense"),
            },
        ],
    }

    if grades.player_type == "pitcher":
        return [pitching_section, general_section, defense_section, hitting_section]
    else:
        return [hitting_section, general_section, defense_section, pitching_section]


# ── Auth helpers ──────────────────────────────────────────────────────────────


def _injured_player_ids(db, team_id: str, league_id: str = "") -> dict:
    """Return dict of {player_id: games_remaining} for players on IL for a team."""
    return InjuryRepository(db, league_id).get_team_injuries(team_id)


def _games_remaining(db, season_id: str | None) -> int:
    """Return the number of unplayed games remaining in a season."""
    return GameRepository(db).games_remaining(season_id)


# ── Landing / Auth ─────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
def landing(request: Request, user: OptionalUser):
    if user:
        return RedirectResponse("/leagues/")
    return templates.TemplateResponse(request, "landing.html", {})


@router.post("/auth/guest")
def create_guest(
    db: DB,
    user: OptionalUser,
    display_name: str = Form(default="Guest"),
):
    """
    Create a guest identity (users row only).
    If a valid session cookie already exists, reuse that user rather than
    creating a new one — prevents identity fragmentation on repeat visits.
    """
    if user:
        return RedirectResponse("/leagues/", status_code=302)

    token = uuid.uuid4().hex + uuid.uuid4().hex
    user_id = str(uuid.uuid4())
    user_repo = UserRepository(db)
    user_repo.insert_user(user_id, token, display_name or "Guest")
    db.commit()
    resp = RedirectResponse("/leagues/", status_code=302)
    resp.set_cookie(
        "gm_session",
        token,
        max_age=60 * 60 * 24 * 365 * 5,
        httponly=True,
        samesite="lax",
    )
    return resp


@router.post("/auth/logout")
def logout(db: DB, user: OptionalUser):
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie("gm_session", httponly=True, samesite="lax")

    if user:
        UserRepository(db).invalidate_session(user["id"])
        db.commit()
    return resp


# ── League list ────────────────────────────────────────────────────────────────


@router.get("/leagues/", response_class=HTMLResponse)
def leagues_index(
    request: Request,
    db: DB,
    user: User,
):
    gm_repo = GMRepository(db)
    # 1. Identity Reclaim (Auto-linking)
    # We still need this for now since we aren't doing 2FA/Logins yet,
    # but the dependency ensures 'user' is already valid.
    # Auto-reclaim: any gm row with same display_name but different user_id
    # gets reassigned to the current user. This handles the common case where
    # the browser cookie was cleared and a new guest identity was created.
    gm_repo.auto_link_gm_account(user["id"], user["display_name"])

    db.commit()

    # 2. Fetch User's Leagues
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
    # print(user["id"])

    gm_id = gm_repo.create_gm(
        league_id=league_id,
        user_id=user["id"],
        display_name=user["display_name"],
    )
    # print(gm_id)
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
    try:
        start_league(league_id, db)
        db.commit()
    except Exception:
        # Surface the error as a plain response so we can see what went wrong
        db.rollback()
        return HTMLResponse(
            f"<pre style='font-family:monospace;padding:24px;background:#0c0f1a;color:#ef4444;'>"
            f"Start league failed:\n\n{traceback.format_exc()}</pre>",
            status_code=500,
        )

    return RedirectResponse(f"/leagues/{league_id}/", status_code=302)


# ── Draft actions ──────────────────────────────────────────────────────────────


@router.put("/leagues/{league_id}/draft/preferences")
async def save_draft_preferences(
    request: Request,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
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

    body = await request.json()
    player_ids = body.get("player_ids", [])
    if not player_ids:
        return JSONResponse({"detail": "player_ids required"}, status_code=422)

    missing = draft_repo.validate_player_ids(player_ids)
    if missing:
        return JSONResponse({"detail": f"Unknown player: {missing}"}, status_code=422)

    draft_repo.save_preferences(draft["id"], gm["id"], player_ids)
    db.commit()

    return JSONResponse({"saved": len(player_ids)})


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
    ctx = _shell_ctx(request, db, gm, league_id, "draft", user)

    draft_repo = DraftRepository(db)
    draft = draft_repo.get_current_for_league(league_id)
    player_repo = PlayerRepository(db)

    if draft:
        picked_ids = draft_repo.get_picked_ids(draft["id"])
        all_players = draft_repo.get_prospects(league_id)

        board = []
        for row in all_players:
            if row["id"] in picked_ids:
                continue
            skills = player_repo.get_player_skills(row["id"])
            grades = player_row_to_grades(dict(row), skills, row["status"])
            ratings = _compute_ratings(skills, dict(row).get("throws", "R"))
            g = grades.model_dump()
            # Prospects use prospect rating for overall
            if ratings:
                g["overall"] = skill_to_grade(ratings.get("prospect"))
                g["best_def_grade"] = skill_to_grade(ratings.get("best_def"))
                g["best_def_label"] = ratings.get("best_def_label", "DEF")
            if g.get("player_type") == "pitcher":
                g["ground_balls"] = skill_to_grade(skills.get("ground_balls"))
            board.append(g)

        prefs = draft_repo.get_preferences(draft["id"], gm["id"]) if gm else []

        pick_position = None
        if gm["team_id"]:
            pick_position = draft_repo.get_pick_position(draft["id"], gm["team_id"])

        ctx["draft_id"] = draft["id"]
        ctx["board"] = board
        ctx["preferences"] = prefs
        ctx["pick_position"] = pick_position
    else:
        ctx["draft_id"] = None
        ctx["board"] = []
        ctx["preferences"] = []
        ctx["pick_position"] = None

    # Load GM's current roster for the right-hand column
    players = []
    if gm["team_id"]:
        roster_rows = player_repo.get_team_roster_with_skills(gm["team_id"])
        for row in roster_rows:

            skills = player_repo.get_player_skills(row["id"])
            d = dict(row)

            grades = player_row_to_grades(d, skills, d["status"])
            ratings = _compute_ratings(skills, d.get("throws", "R"))
            g = grades.model_dump()
            if ratings:
                if g.get("player_type") == "pitcher":
                    best_p = max(ratings.get("sp", 0), ratings.get("rp", 0))
                    g["overall"] = skill_to_grade(best_p) if best_p else g["overall"]
                else:
                    g["overall"] = skill_to_grade(ratings.get("overall_player"))
                g["best_def_grade"] = skill_to_grade(ratings.get("best_def"))
                g["best_def_label"] = ratings.get("best_def_label", "DEF")
            if g.get("player_type") == "pitcher":
                g["ground_balls"] = skill_to_grade(skills.get("ground_balls"))
            players.append(g)
    ctx["players"] = players

    return tab_response(request, htmx, "dashboard/partials/draft.html", ctx)


@router.post("/leagues/{league_id}/draft/execute")
def execute_draft(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
):
    """Execute the blitz auto-draft and redirect to results."""
    draft = DraftRepository(db).get_current_for_league(league_id)

    if not draft:
        return RedirectResponse(f"/leagues/{league_id}/draft", status_code=302)

    # If already complete, just go to results
    if draft["state"] == "complete":
        return RedirectResponse(f"/leagues/{league_id}/draft/results", status_code=302)

    try:
        execute_blitz_draft(draft["id"], db)
        db.commit()
    except Exception:
        db.rollback()
        return HTMLResponse(
            f"<pre style='font-family:monospace;padding:24px;background:#0c0f1a;color:#ef4444;'>"
            f"Draft execution failed:\n\n{traceback.format_exc()}</pre>",
            status_code=500,
        )

    return RedirectResponse(f"/leagues/{league_id}/draft/results", status_code=302)


@router.get("/leagues/{league_id}/draft/results", response_class=HTMLResponse)
def draft_results(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    """Show completed draft results — all picks by round, your picks highlighted."""
    ctx = _shell_ctx(request, db, gm, league_id, "draft", user)

    draft_repo = DraftRepository(db)
    draft = draft_repo.get_current_for_league(league_id)

    rounds = []
    my_team_id = gm["team_id"]

    if draft:
        picks = draft_repo.get_picks_with_details(draft["id"])

        gm_repo = GMRepository(db)
        human_team_ids = gm_repo.get_human_team_ids(league_id)

        # Group by round
        rounds_map = {}
        for pick in picks:
            r = pick["round"]
            if r not in rounds_map:
                rounds_map[r] = []
            is_mine = pick["team_id"] == my_team_id
            is_human = pick["team_id"] in human_team_ids and not is_mine
            rounds_map[r].append(
                {
                    "pick_number": pick["pick_number"],
                    "team_id": pick["team_id"],
                    "player_id": pick["player_id"],
                    "team_name": f"{pick['city']} {pick['mascot']}",
                    "player_name": f"{pick['first_name']} {pick['last_name']}",
                    "position": pick["position"] or "%s",
                    "auto_picked": bool(pick["auto_picked"]),
                    "is_mine": is_mine,
                    "is_human": is_human,
                }
            )
        rounds = [
            {"round": r, "picks": picks} for r, picks in sorted(rounds_map.items())
        ]

    ctx["rounds"] = rounds
    ctx["draft_done"] = bool(draft and draft["state"] == "complete")
    return tab_response(request, htmx, "dashboard/partials/draft_results.html", ctx)


@router.post("/leagues/{league_id}/roster/save", response_class=HTMLResponse)
def save_roster(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
):
    """Save 40-man roster. Enforces the 40-player limit."""
    # Read JSON body
    _ = (
        asyncio.get_event_loop().run_until_complete(request.body())
        if hasattr(request, "_body")
        else None
    )

    return HTMLResponse("ok")  # placeholder — real logic below


@router.put("/leagues/{league_id}/roster/save")
def save_roster_put(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
):
    """PUT endpoint for roster save from JS fetch."""
    team_id = gm["team_id"]

    # Parse body synchronously via stored body
    body = None
    try:
        loop = asyncio.new_event_loop()
        body = loop.run_until_complete(request.json())
        loop.close()
    except Exception:
        return JSONResponse({"detail": "Invalid JSON"}, status_code=422)

    forty_man_ids = body.get("forty_man", [])

    if len(forty_man_ids) > 40:
        return JSONResponse(
            {
                "detail": f"40-man roster cannot exceed 40 players ({len(forty_man_ids)} submitted)"
            },
            status_code=422,
        )

    player_repo = PlayerRepository(db)
    status_repo = PlayerStatusRepository(db)
    team_player_ids = player_repo.get_player_ids_from_team_players(team_id)

    for pid in forty_man_ids:
        if pid not in team_player_ids:
            return JSONResponse(
                {"detail": f"Player {pid} not on this team"}, status_code=422
            )

    status_repo.set_40man_roster(team_player_ids, forty_man_ids)
    db.commit()
    return JSONResponse({"saved": len(forty_man_ids)})


# ── Sim ─────────────────────────────────────────────────────────────────────────


@router.post("/leagues/{league_id}/sim")
async def sim_games(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
):
    """Sim N games (or until season end). Returns JSON with results summary."""
    body = await request.json()
    count = body.get("count", 1)  # number of game-days to sim, or "season"

    season_repo = SeasonRepository(db)
    league_repo = LeagueRepository(db)

    results = []
    days_simmed = 0
    all_new_injuries = []
    all_returned = []
    remaining = _games_remaining(db, season_repo.get_current_id_for_league(league_id))

    limit = remaining if count == "season" else min(int(count), remaining)

    for _ in range(limit):
        day_result = sim_next_day(league_id, db)
        gp = day_result.get("games_played", 0)
        if gp > 0:
            results.append(day_result)
            days_simmed += 1
            all_new_injuries.extend(day_result.get("new_injuries", []))
            all_returned.extend(day_result.get("returned", []))
        # Stop if season ended (no game_date) or if state changed out of season
        if not day_result.get("game_date"):
            break
        # Stop if no games played and it wasn't a transient error
        if gp == 0 and not day_result.get("errors"):
            break

    games_played = sum(r.get("games_played", 0) for r in results)
    new_remaining = _games_remaining(
        db, season_repo.get_current_id_for_league(league_id)
    )
    # If season just ended, trigger the state transition (playoffs setup)
    if new_remaining == 0 and days_simmed > 0:
        sim_next_day(league_id, db)

    league = league_repo.get_by_id(league_id)
    league_state = league["state"] if league else "lobby"
    current_season_id = season_repo.get_current_id_for_league(league_id)
    current_date = _current_league_date(db, current_season_id, league_state)

    return JSONResponse(
        {
            "days_simmed": days_simmed,
            "games_played": games_played,
            "games_remaining": new_remaining,
            "last_date": results[-1]["game_date"] if results else None,
            "league_state": league_state,
            "current_date": current_date,
            "new_injuries": all_new_injuries,
            "returned": all_returned,
        }
    )


# ── Tab: Standings ─────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/standings", response_class=HTMLResponse)
def standings(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    ctx = _shell_ctx(request, db, gm, league_id, "standings", user)
    season_id = ctx["season_id"]
    my_team_id = gm["team_id"] if gm else None
    teams = []

    if season_id:
        # tg_repo = TeamGameRepository(db)
        game_repo = GameRepository(db)
        gm_repo = GMRepository(db)
        inj_repo = InjuryRepository(db, league_id)

        st_repo = StandingsRepository(db)
        ra_map = st_repo.get_runs_allowed(season_id)
        ha_map = st_repo.get_home_away_splits(season_id)
        human_team_ids = gm_repo.get_human_team_ids(league_id)
        recent_rows = st_repo.get_recent_results(season_id)

        # Build per-team recent results
        team_recent: dict[str, list] = {}
        for r in recent_rows:
            tid = r["team_id"]
            if tid not in team_recent:
                team_recent[tid] = []
            if len(team_recent[tid]) < 10:
                team_recent[tid].append(r["win"])

        def calc_streak(results: list) -> str:
            """results[0] is most recent game"""
            if not results:
                return "—"
            letter = "W" if results[0] else "L"
            count = 0
            for r in results:
                if bool(r) == (letter == "W"):
                    count += 1
                else:
                    break
            return f"{letter}{count}"

        # Sort by win pct descending, with H2H and RS tiebreakers
        rows = st_repo.get_records(league_id, season_id)
        raw_rows = [
            {
                **r,
                "win_pct": (
                    r["wins"] / (r["wins"] + r["losses"])
                    if (r["wins"] + r["losses"])
                    else 0.0
                ),
            }
            for r in rows
        ]
        ranked = st_repo.sort(season_id, raw_rows)
        leader_wins = ranked[0]["wins"] or 0 if ranked else 0
        leader_losses = ranked[0]["losses"] or 0 if ranked else 0

        for rank, r in enumerate(ranked, 1):
            wins = r["wins"] or 0
            losses = r["losses"] or 0
            _ = r["runs_scored"] or 0
            _ = ra_map.get(r["team_id"], 0)
            played = wins + losses
            pct = wins / played if played else 0.0
            gb_val = ((leader_wins - wins) + (losses - leader_losses)) / 2
            gb = (
                "—"
                if rank == 1
                else (f"{gb_val:.1f}" if gb_val != int(gb_val) else str(int(gb_val)))
            )
            recent = team_recent.get(r["team_id"], [])
            rs = r["runs_scored"] or 0
            ra = ra_map.get(r["team_id"], 0)
            ha = ha_map.get(r["team_id"], {"hw": 0, "hl": 0, "aw": 0, "al": 0})
            l10_wins = sum(1 for w in recent[:10] if w)
            l10_losses = 10 - l10_wins if len(recent) >= 10 else len(recent) - l10_wins
            pct_str = f"{pct:.3f}"
            pct_str = pct_str[1:] if pct_str.startswith("0") else pct_str
            teams.append(
                {
                    "rank": rank,
                    "team_id": r["team_id"],
                    "city": r["city"],
                    "mascot": r["mascot"],
                    "wins": wins,
                    "losses": losses,
                    "pct": pct_str,
                    "gb": gb,
                    "streak": calc_streak(recent),
                    "home": f"{ha['hw']}-{ha['hl']}",
                    "away": f"{ha['aw']}-{ha['al']}",
                    "l10": f"{l10_wins}-{l10_losses}",
                    "rs": rs,
                    "ra": ra,
                    "is_human": r["team_id"] in human_team_ids,
                    "is_mine": r["team_id"] == my_team_id,
                }
            )

        # ── My next 3 upcoming games ──────────────────────────────────────────
        upcoming = []
        if my_team_id:
            for g_row in game_repo.get_team_upcoming(season_id, my_team_id, limit=3):
                is_home = g_row["home_team_id"] == my_team_id
                opp_city = g_row["away_city"] if is_home else g_row["home_city"]
                opp_mascot = g_row["away_mascot"] if is_home else g_row["home_mascot"]
                upcoming.append(
                    {
                        "date": g_row["game_date"],
                        "home_away": "vs" if is_home else "@",
                        "opponent": f"{opp_city} {opp_mascot}",
                    }
                )

        # ── My last 5 completed games ─────────────────────────────────────────
        recent_games = []
        if my_team_id:
            for g_row in game_repo.get_team_results(season_id, my_team_id, limit=5):
                is_home = g_row["home_team_id"] == my_team_id
                my_score = g_row["home_score"] if is_home else g_row["away_score"]
                opp_score = g_row["away_score"] if is_home else g_row["home_score"]
                opp_city = g_row["away_city"] if is_home else g_row["home_city"]
                opp_mascot = g_row["away_mascot"] if is_home else g_row["home_mascot"]
                won = (my_score or 0) > (opp_score or 0)
                recent_games.append(
                    {
                        "game_id": g_row["game_id"],
                        "date": g_row["game_date"],
                        "home_away": "vs" if is_home else "@",
                        "opponent": f"{opp_city} {opp_mascot}",
                        "my_score": my_score,
                        "opp_score": opp_score,
                        "result": "W" if won else "L",
                    }
                )

        # ── Injury report ─────────────────────────────────────────────────────
        injuries = []
        if my_team_id:
            injuries = inj_repo.get_team_injury_report(my_team_id, league_id)

    else:
        upcoming = []
        recent_games = []
        injuries = []

    ctx["teams"] = teams
    ctx["games_played"] = (
        sum(t["wins"] + t["losses"] for t in teams) // 2 if teams else 0
    )
    ctx["upcoming"] = upcoming
    ctx["recent_games"] = recent_games
    ctx["injuries"] = injuries
    ctx["my_team_id"] = my_team_id
    return tab_response(request, htmx, "dashboard/partials/standings.html", ctx)


# ── Tab: Leaders ───────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/leaders", response_class=HTMLResponse)
def leaders(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
    category: str = "batting",
    season: str | None = None,
):
    ctx = _shell_ctx(request, db, gm, league_id, "leaders", user)
    my_team_id = gm["team_id"] if gm else None

    sr = SeasonRepository(db)
    all_seasons = sr.get_seasons_for_league(league_id)  # newest first

    # Determine which season to display: explicit param > last with completed games
    last_completed = sr.get_last_with_completed_games(league_id)
    if season and any(s["id"] == season for s in all_seasons):
        display_season = next(s for s in all_seasons if s["id"] == season)
    elif last_completed:
        display_season = last_completed
    else:
        display_season = all_seasons[0] if all_seasons else None

    season_id = display_season["id"] if display_season else None
    ctx["leaders_season_id"] = season_id
    ctx["leaders_season_name"] = display_season["name"] if display_season else ""
    ctx["leaders_seasons"] = all_seasons

    bat_cats = []
    pit_cats = []

    if season_id:
        pss_repo = PlayerSeasonStatsRepository(db)

        team_games = pss_repo.get_max_games_played(season_id)
        min_ab = int(3.1 * team_games)  # qualify for rate stats
        min_outs = int(3 * team_games)  # 1 IP per team game

        bat_rows = pss_repo.get_batting_for_league(league_id, season_id)

        batters = []
        for r in bat_rows:
            ab = r["bat_ab"] or 0
            h = r["bat_hits"] or 0
            d = r["bat_doubles"] or 0
            tr = r["bat_triples"] or 0
            hr = r["bat_home_runs"] or 0
            rbi = r["bat_rbi"] or 0
            runs = r["bat_runs"] or 0
            bb = r["bat_walks"] or 0
            k = r["bat_strike_outs"] or 0
            sb = r["bat_stolen_bases"] or 0
            hbp = r["bat_hbp"] or 0
            sf = r["bat_sac_flys"] or 0
            avg = h / ab if ab else 0.0
            obp_d = ab + bb + hbp + sf
            obp = (h + bb + hbp) / obp_d if obp_d else 0.0
            tb = h - d - tr - hr + 2 * d + 3 * tr + 4 * hr
            slg = tb / ab if ab else 0.0
            qualifies = ab >= min_ab
            ab_k = ab / k if k else 0.0
            ab_hr = ab / hr if hr else None
            bb_k = bb / k if k else None
            batters.append(
                {
                    "player_id": r["player_id"],
                    "name": f"{r['first_name']} {r['last_name']}",
                    "team": f"{r['city']} {r['mascot']}",
                    "team_id": r["team_id"],
                    "is_mine": r["team_id"] == my_team_id,
                    "qualifies": qualifies,
                    "AVG": avg,
                    "HR": hr,
                    "RBI": rbi,
                    "R": runs,
                    "H": h,
                    "SB": sb,
                    "OBP": obp,
                    "SLG": slg,
                    "OPS": obp + slg,
                    "2B": d,
                    "3B": tr,
                    "BB": bb,
                    "K": k,
                    "AB/K": ab_k,
                    "AB/HR": ab_hr,
                    "BB/K": bb_k,
                }
            )

        def bat_card(label, key, pool=None, asc=False, fmt=None):
            srt = sorted(
                pool if pool is not None else batters,
                key=lambda r: r[key],
                reverse=not asc,
            )[:10]
            rows = []
            for i, r in enumerate(srt, 1):
                val = r[key]
                disp = (
                    fmt(val)
                    if fmt
                    else (
                        str(int(val))
                        if isinstance(val, float) and val == int(val)
                        else (f"{val:.3f}" if isinstance(val, float) else str(val))
                    )
                )
                rows.append(
                    {
                        "rank": i,
                        "name": r["name"],
                        "team": r["team"],
                        "player_id": r["player_id"],
                        "is_mine": r["is_mine"],
                        "val": disp,
                    }
                )
            return {"label": label, "rows": rows}

        qualified = [b for b in batters if b["qualifies"]]
        all_bat = batters  # no AB minimum for counting stats

        def bat_card_q(label, key, pool=None, asc=False, fmt=None):
            return bat_card(label, key, pool=pool or qualified, asc=asc, fmt=fmt)

        bat_cats = [
            bat_card_q("AVG", "AVG", fmt=lambda v: f"{v:.3f}"[1:]),
            bat_card("HR", "HR", pool=all_bat),
            bat_card("RBI", "RBI", pool=all_bat),
            bat_card("R", "R", pool=all_bat),
            bat_card("H", "H", pool=all_bat),
            bat_card("SB", "SB", pool=all_bat),
            bat_card_q("OBP", "OBP", fmt=lambda v: f"{v:.3f}"[1:]),
            bat_card_q("SLG", "SLG", fmt=lambda v: f"{v:.3f}"),
            bat_card_q("OPS", "OPS", fmt=lambda v: f"{v:.3f}"),
            bat_card("2B", "2B", pool=all_bat),
            bat_card("3B", "3B", pool=all_bat),
            bat_card("BB", "BB", pool=all_bat),
            bat_card_q("AB/K", "AB/K", fmt=lambda v: f"{v:.1f}"),
            bat_card(
                "AB/HR",
                "AB/HR",
                pool=[b for b in qualified if b["AB/HR"] is not None],
                asc=True,
                fmt=lambda v: f"{v:.1f}",
            ),
            bat_card(
                "BB/K",
                "BB/K",
                pool=[b for b in qualified if b["BB/K"] is not None],
                fmt=lambda v: f"{v:.2f}",
            ),
        ]

        pit_rows = pss_repo.get_pitching_for_league(league_id, season_id)

        pitchers = []
        for r in pit_rows:
            outs = r["pitch_outs"] or 0
            er = r["pitch_earned_runs"] or 0
            ph = r["pitch_hits"] or 0
            pbb = r["pitch_walks"] or 0
            pk = r["pitch_strike_outs"] or 0
            hr = r["pitch_home_runs"] or 0
            ip_f = outs / 3
            era = (er * 27) / outs if outs else 0.0
            whip = (pbb + ph) / ip_f if ip_f else 0.0
            qualifies_p = outs >= min_outs
            bb9 = (pbb * 27) / outs if outs else 0.0
            hr9 = (hr * 27) / outs if outs else 0.0
            k9 = (pk * 27) / outs if outs else 0.0
            pitchers.append(
                {
                    "player_id": r["player_id"],
                    "name": f"{r['first_name']} {r['last_name']}",
                    "team": f"{r['city']} {r['mascot']}",
                    "team_id": r["team_id"],
                    "is_mine": r["team_id"] == my_team_id,
                    "qualifies": qualifies_p,
                    "ERA": era,
                    "WHIP": whip,
                    "W": r["pitch_wins"] or 0,
                    "K": pk,
                    "SV": r["pitch_saves"] or 0,
                    "IP": ip_f,
                    "BB/9": bb9,
                    "HR/9": hr9,
                    "K/9": k9,
                }
            )

        def pit_card(label, key, pool=None, asc=False, fmt=None):
            srt = sorted(
                pool if pool is not None else pitchers,
                key=lambda r: r[key],
                reverse=not asc,
            )[:10]
            rows = []
            for i, r in enumerate(srt, 1):
                val = r[key]
                if fmt:
                    disp = fmt(val)
                elif key == "IP":
                    o = int(val * 3)
                    disp = f"{o//3}.{o%3}"
                else:
                    disp = str(int(val)) if val == int(val) else f"{val:.2f}"
                rows.append(
                    {
                        "rank": i,
                        "name": r["name"],
                        "team": r["team"],
                        "player_id": r["player_id"],
                        "is_mine": r["is_mine"],
                        "val": disp,
                    }
                )
            return {"label": label, "rows": rows}

        q_pit = [p for p in pitchers if p["qualifies"]]
        all_pit = pitchers

        def pit_card_q(label, key, asc=False, fmt=None):
            return pit_card(label, key, pool=q_pit, asc=asc, fmt=fmt)

        pit_cats = [
            pit_card_q("ERA", "ERA", asc=True, fmt=lambda v: f"{v:.2f}"),
            pit_card_q("WHIP", "WHIP", asc=True, fmt=lambda v: f"{v:.2f}"),
            pit_card("W", "W", pool=all_pit),
            pit_card("K", "K", pool=all_pit),
            pit_card("SV", "SV", pool=all_pit),
            pit_card_q("IP", "IP"),
            pit_card_q("BB/9", "BB/9", asc=True, fmt=lambda v: f"{v:.2f}"),
            pit_card_q("HR/9", "HR/9", asc=True, fmt=lambda v: f"{v:.2f}"),
            pit_card_q("K/9", "K/9", fmt=lambda v: f"{v:.2f}"),
        ]

    ctx["category"] = category
    ctx["bat_cats"] = bat_cats
    ctx["pit_cats"] = pit_cats
    return tab_response(request, htmx, "dashboard/partials/leaders.html", ctx)


# ── Tab: Roster ────────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/roster", response_class=HTMLResponse)
def roster(
    request: Request,
    htmx: IsHTMX,
    db: DB,
    user: User,
    gm: GM,
    league_id: str,
):
    ctx = _shell_ctx(request, db, gm, league_id, "roster", user)
    players = []
    team_id = gm["team_id"]

    if team_id:
        player_repo = PlayerRepository(db)
        for row in player_repo.get_team_roster_with_skills(team_id):
            d = row
            grades = player_row_to_grades(d, d, d["status"])
            ratings = _compute_ratings(d, d.get("throws", "R"))
            g = grades.model_dump()
            if ratings:
                if g.get("player_type") == "pitcher":
                    best_p = max(ratings.get("sp", 0), ratings.get("rp", 0))
                    g["overall"] = skill_to_grade(best_p) if best_p else g["overall"]
                    g["sp_grade"] = skill_to_grade(ratings.get("sp", 0))
                    g["rp_grade"] = skill_to_grade(ratings.get("rp", 0))
                else:
                    g["overall"] = skill_to_grade(ratings.get("overall_player"))
                g["best_def_grade"] = skill_to_grade(ratings.get("best_def"))
                g["best_def_label"] = ratings.get("best_def_label", "DEF")
                g["if_grade"] = skill_to_grade(ratings.get("if", 0))
                g["of_grade"] = skill_to_grade(ratings.get("of", 0))
                g["c_grade"] = skill_to_grade(ratings.get("c", 0))
                g["b1_grade"] = skill_to_grade(ratings.get("1b", 0))
            g["base_running"] = skill_to_grade(d.get("base_running"))
            g["bunting"] = skill_to_grade(d.get("bunting"))
            g["ground_balls"] = skill_to_grade(d.get("ground_balls"))
            players.append(g)

    # Season stats for display on roster cards
    season_id = ctx.get("season_id")
    if season_id and team_id:
        stats_map = PlayerSeasonStatsRepository(db).get_team_stats_map(
            season_id, team_id
        )
        for p in players:
            s = stats_map.get(p["player_id"])
            if s and p.get("player_type") != "pitcher":
                ab = s["bat_ab"] or 0
                p["stat_g"] = s["bat_games_played"] or 0
                p["stat_avg"] = f"{s['bat_hits']/ab:.3f}" if ab else None
                p["stat_hr"] = s["bat_home_runs"] or 0
                p["stat_rbi"] = s["bat_rbi"] or 0
            elif s and p.get("player_type") == "pitcher":
                outs = s["pitch_outs"] or 0
                p["stat_gs"] = s["pitch_games_started"] or 0
                p["stat_ip"] = f"{outs//3}.{outs%3}" if outs else None
                p["stat_era"] = (
                    f"{(s['pitch_earned_runs']*27)/outs:.2f}" if outs else None
                )
                p["stat_w"] = s["pitch_wins"] or 0
                p["stat_l"] = s["pitch_losses"] or 0
                p["stat_sv"] = s["pitch_saves"] or 0

    injured_ids = _injured_player_ids(db, team_id, league_id)
    for p in players:
        raw_days = injured_ids.get(p["player_id"])
        p["injured"] = raw_days is not None
        p["injury_days"] = raw_days if raw_days else None
        p["returning"] = False
    ctx["players"] = players
    return tab_response(request, htmx, "dashboard/partials/roster.html", ctx)


# ── Tab: Lineup ────────────────────────────────────────────────────────────────


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

    team_id = gm["team_id"]
    season_id = ctx.get("season_id")

    # For stat display use last season with completed games so preseason still
    # shows last year's numbers when building the new lineup.
    _stats_s = SeasonRepository(db).get_last_with_completed_games(league_id)
    stats_season_id = _stats_s["id"] if _stats_s else season_id

    # Load all 40-man players with grades (skills batched in the query)
    player_repo = PlayerRepository(db)
    hitters = []
    pitchers = []
    for row in player_repo.get_active_roster_with_skills(team_id):
        d = row
        grades = player_row_to_grades(d, d, d["status"])
        ratings = _compute_ratings(d, d.get("throws", "R"))
        g = grades.model_dump()
        if ratings:
            if g.get("player_type") == "pitcher":
                best_p = max(ratings.get("sp", 0), ratings.get("rp", 0))
                g["overall"] = skill_to_grade(best_p) if best_p else g["overall"]
                g["sp_grade"] = skill_to_grade(ratings.get("sp", 0))
                g["rp_grade"] = skill_to_grade(ratings.get("rp", 0))
                g["bat_overall"] = skill_to_grade(ratings.get("overall_player"))
            else:
                g["overall"] = skill_to_grade(ratings.get("overall_player"))
                g["leadoff_grade"] = skill_to_grade(ratings.get("lead_off", 0))
                g["power_h_grade"] = skill_to_grade(ratings.get("power_hitter", 0))
                g["contact_h_grade"] = skill_to_grade(ratings.get("contact_hitter", 0))
                g["oofense_h_grade"] = skill_to_grade(ratings.get("offense", 0))
                g["bat_overall"] = g["overall"]
            g["best_def_grade"] = skill_to_grade(ratings.get("best_def"))
            g["best_def_label"] = ratings.get("best_def_label", "DEF")
            # Per-position ratings for assigned-position display
            for pos in (
                "c",
                "1b",
                "2b",
                "3b",
                "ss",
                "lf",
                "cf",
                "rf",
                "of",
                "if",
                "dh",
            ):
                g[f"pos_{pos}"] = skill_to_grade(ratings.get(pos, 0))
        # Raw skill grades not in PlayerGrades — needed for sort and batting display
        g["base_running"] = skill_to_grade(d.get("base_running"))
        g["bunting"] = skill_to_grade(d.get("bunting"))
        g["ground_balls"] = skill_to_grade(d.get("ground_balls"))
        # Hitting grades for all players — pitchers need these when batting
        if g.get("contact") is None:
            g["contact"] = skill_to_grade(d.get("contact"))
        if g.get("power") is None:
            g["power"] = skill_to_grade(d.get("power"))
        if g.get("eye") is None:
            g["eye"] = skill_to_grade(d.get("eye"))
        if g.get("speed") is None:
            g["speed"] = skill_to_grade(d.get("speed"))
        if g.get("arm") is None:
            g["arm"] = skill_to_grade(d.get("arm"))
        if g.get("player_type") == "pitcher":
            pitchers.append(g)
        else:
            hitters.append(g)

    # Load saved lineup preferences, rotation, bullpen
    lp_repo = LineupPreferenceRepository(db)
    rot_repo = TeamRotationsRepository(db)
    bp_repo = BullpenRepository(db)

    saved_lineup = lp_repo.get_by_gm_id(gm["id"])
    saved_rotation = (
        rot_repo.get_saved_rotation(team_id, season_id) if season_id else []
    )
    saved_bullpen = bp_repo.get_roles_map(team_id, season_id) if season_id else {}
    saved_rotation_pointer = (
        rot_repo.get_rotation_pointer_player(team_id, season_id)
        if season_id and saved_rotation
        else None
    )

    # Attach season stats to each player for display
    if stats_season_id:
        stats_map = PlayerSeasonStatsRepository(db).get_team_stats_map(
            stats_season_id, team_id
        )
        for p in hitters:
            s = stats_map.get(p["player_id"])
            if s and (s["bat_ab"] or 0) > 0:
                avg = s["bat_hits"] / s["bat_ab"]
                p["stat_avg"] = f"{avg:.3f}"
                p["stat_hr"] = s["bat_home_runs"] or 0
            else:
                p["stat_avg"] = None
                p["stat_hr"] = None
        for p in pitchers:
            s = stats_map.get(p["player_id"])
            if s and (s["bat_ab"] or 0) > 0:
                avg = s["bat_hits"] / s["bat_ab"]
                p["stat_avg"] = f"{avg:.3f}"
                p["stat_hr"] = s["bat_home_runs"] or 0
            else:
                p["stat_avg"] = None
                p["stat_hr"] = None
            if s and (s["pitch_games_played"] or 0) > 0:
                outs = s["pitch_outs"] or 0
                p["stat_gs"] = s["pitch_games_started"] or 0
                p["stat_era"] = (
                    f"{(s['pitch_earned_runs'] * 27) / outs:.2f}" if outs else "--"
                )
                p["stat_ip"] = f"{outs // 3}.{outs % 3}"
                p["stat_w"] = s["pitch_wins"] or 0
                p["stat_l"] = s["pitch_losses"] or 0
                p["stat_sv"] = s["pitch_saves"] or 0
            else:
                p["stat_gs"] = None
                p["stat_era"] = None
                p["stat_ip"] = None
                p["stat_w"] = None
                p["stat_l"] = None
                p["stat_sv"] = None

    injured_map = _injured_player_ids(db, team_id, league_id)
    for p in hitters + pitchers:
        raw_days = injured_map.get(p["player_id"])
        p["injured"] = raw_days is not None
        p["injury_days"] = raw_days if raw_days else None
        p["returning"] = False
    ctx["hitters"] = hitters
    ctx["pitchers"] = pitchers
    ctx["saved_lineup"] = saved_lineup
    ctx["saved_rotation"] = saved_rotation
    ctx["saved_bullpen"] = saved_bullpen
    ctx["saved_rotation_pointer"] = saved_rotation_pointer
    # Tell template whether we're in playoffs so the nav button points the right way
    league_row = LeagueRepository(db).get_by_id(league_id)
    ctx["is_playoffs"] = league_row and league_row["state"] == "playoffs"
    return tab_response(request, htmx, "dashboard/partials/lineup.html", ctx)


@router.put("/leagues/{league_id}/lineup/save")
async def save_lineup_prefs(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
):
    if not gm["team_id"]:
        return JSONResponse({"detail": "No team"}, status_code=400)

    body = await request.json()
    lineup = body.get("lineup", [])  # [{player_id, batting_order, position}]

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

    db.commit()
    return JSONResponse({"saved": True})


@router.put("/leagues/{league_id}/rotation/save")
async def save_rotation(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
):
    if not gm["team_id"]:
        return JSONResponse({"detail": "No team"}, status_code=400)

    body = await request.json()
    rotation = body.get("rotation", [])
    pointer_pid = body.get("pointer_pid", None)
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
    except (ValueError, TypeError):
        # Fallback if the pointer_pid is missing or not in the rotation
        next_order = 1

    rot_repo = TeamRotationsRepository(db)
    rot_repo.replace_rotation(
        team_id=team_id,
        season_id=season_id,
        player_ids=rotation,
        effective_date=effective_date,
        next_order=next_order,
    )

    db.commit()
    return JSONResponse({"saved": True})


@router.put("/leagues/{league_id}/bullpen/save")
async def save_bullpen(
    league_id: str,
    body: BullpenSaveRequest,
    db: DB,
    gm: GM,
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
    rot_repo = TeamRotationsRepository(db)

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
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))

    return JSONResponse({"saved": True})


# ── Tab: Strategy ──────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/strategy", response_class=HTMLResponse)
def strategy(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    ctx = _shell_ctx(request, db, gm, league_id, "strategy", user)

    profile_row = GMRepository(db).get_profile(gm["id"])

    _L = ["traditional", "analytics", "speed-first", "power-first"]
    _S = ["conservative", "standard", "aggressive"]
    _B = ["never", "situational", "frequent"]
    _P = ["none", "vs-handedness", "aggressive"]
    _U = ["let-them-work", "pitch-count-strict", "matchup-based"]
    _C = ["saves-only", "high-leverage", "best-available"]
    _N = ["deep-pen", "starter-heavy"]

    def idx(lst, val, default=0):
        try:
            return lst.index(val)
        except:
            return default

    if profile_row:
        p = profile_row
        ctx["profile"] = {
            "lineup_style_index": idx(_L, p.get("lineup_style", "analytics"), 1),
            "steal_aggression_index": idx(_S, p.get("steal_aggression", "standard"), 1),
            "sac_bunt_index": idx(_B, p.get("sac_bunt", "situational"), 1),
            "platoon_usage_index": idx(_P, p.get("platoon_usage", "none"), 0),
            "starter_usage_index": idx(
                _U, p.get("starter_usage", "pitch-count-strict"), 1
            ),
            "closer_usage_index": idx(_C, p.get("closer_usage", "saves-only"), 0),
            "bullpen_pref_index": idx(_N, p.get("bullpen_pref", "deep-pen"), 0),
        }
    else:
        ctx["profile"] = {
            "lineup_style_index": 1,
            "steal_aggression_index": 1,
            "sac_bunt_index": 1,
            "platoon_usage_index": 0,
            "starter_usage_index": 1,
            "closer_usage_index": 0,
            "bullpen_pref_index": 0,
        }

    return tab_response(request, htmx, "dashboard/partials/strategy.html", ctx)


@router.post("/leagues/{league_id}/strategy")
async def save_strategy(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
):
    if not gm:
        return HTMLResponse("Not a member of this league", status_code=403)

    form = await request.form()
    _MAPS = {
        "lineup_style": ["traditional", "analytics", "speed-first", "power-first"],
        "steal_aggression": ["conservative", "standard", "aggressive"],
        "sac_bunt": ["never", "situational", "frequent"],
        "platoon_usage": ["none", "vs-handedness", "aggressive"],
        "starter_usage": ["let-them-work", "pitch-count-strict", "matchup-based"],
        "closer_usage": ["saves-only", "high-leverage", "best-available"],
        "bullpen_pref": ["deep-pen", "starter-heavy"],
    }
    updates = {}
    for field, options in _MAPS.items():
        i = int(form.get(field, 0))
        updates[field] = options[min(i, len(options) - 1)]

    GMRepository(db).save_profile(gm["id"], updates)
    db.commit()
    return HTMLResponse(
        '<span style="color:var(--green);font-family:var(--font-mono);font-size:11px;">✓ Saved</span>'
    )


# ── Tab: Schedule ──────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/schedule", response_class=HTMLResponse)
def schedule(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    ctx = _shell_ctx(request, db, gm, league_id, "schedule", user)
    season_id = ctx["season_id"]
    my_team_id = gm["team_id"] if gm else None

    upcoming = []
    recent = []

    if season_id and my_team_id:
        game_repo = GameRepository(db)
        tg_repo = TeamGameRepository(db)

        up_rows = game_repo.get_team_upcoming(season_id, my_team_id)
        opp_team_ids = {
            r["away_team_id"] if r["home_team_id"] == my_team_id else r["home_team_id"]
            for r in up_rows
        }
        opp_records = tg_repo.get_records_for_teams(season_id, opp_team_ids)

        for r in up_rows:
            is_home = r["home_team_id"] == my_team_id
            opp_id = r["away_team_id"] if is_home else r["home_team_id"]
            upcoming.append(
                {
                    "date": r["game_date"],
                    "home_away": "vs" if is_home else "@",
                    "opp_city": r["away_city"] if is_home else r["home_city"],
                    "opp_mascot": r["away_mascot"] if is_home else r["home_mascot"],
                    "opp_record": opp_records.get(opp_id, "0-0"),
                    "is_home": is_home,
                }
            )

        for r in game_repo.get_team_results(season_id, my_team_id):
            is_home = r["home_team_id"] == my_team_id
            my_score = r["home_score"] if is_home else r["away_score"]
            opp_score = r["away_score"] if is_home else r["home_score"]
            won = (my_score or 0) > (opp_score or 0)
            extra = (
                f" ({r['innings_played']})"
                if r["innings_played"] and r["innings_played"] != 9
                else ""
            )
            recent.append(
                {
                    "game_id": r["game_id"],
                    "date": r["game_date"],
                    "home_away": "vs" if is_home else "@",
                    "opp_city": r["away_city"] if is_home else r["home_city"],
                    "opp_mascot": r["away_mascot"] if is_home else r["home_mascot"],
                    "my_score": my_score,
                    "opp_score": opp_score,
                    "result": "W" if won else "L",
                    "extra": extra,
                }
            )

    ctx["upcoming"] = upcoming
    ctx["recent"] = recent
    return tab_response(request, htmx, "dashboard/partials/schedule.html", ctx)


# ── Tab: Stats ─────────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/stats", response_class=HTMLResponse)
def stats(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
    team_id: str | None = None,
    season_id: str | None = None,
    postseason: int = 0,
):
    ctx = _shell_ctx(request, db, gm, league_id, "stats", user)
    current_season_id = ctx["season_id"]
    my_team_id = gm["team_id"] if gm else None

    season_repo = SeasonRepository(db)
    team_repo = TeamRepository(db)

    # All seasons for this league, newest first
    all_seasons = season_repo.get_seasons_for_league(league_id)

    # Default to current season
    selected_season_id = season_id or current_season_id
    is_postseason = bool(postseason)

    # Default to user's team
    selected_team_id = team_id or my_team_id

    # All teams for the selected season
    all_teams = (
        team_repo.get_teams_in_league_season(league_id, selected_season_id)
        if selected_season_id
        else []
    )

    # If selected team isn't in selected season's teams, reset to first available
    team_ids_in_season = {t["id"] for t in all_teams}
    if selected_team_id and selected_team_id not in team_ids_in_season:
        selected_team_id = all_teams[0]["id"] if all_teams else None

    batters = []
    pitchers = []
    team_games = 0
    # ps_flag = 1 if is_postseason else 0

    if selected_season_id and selected_team_id:
        pss_repo = PlayerSeasonStatsRepository(db)
        team_games = pss_repo.get_max_games_played_for_team(
            selected_season_id, selected_team_id, is_postseason
        )
        min_ab = int(3.1 * team_games) if not is_postseason else 0
        min_outs = int(3 * team_games) if not is_postseason else 0

        rows = pss_repo.get_for_team(
            selected_season_id, selected_team_id, is_postseason
        )

        for s in rows:
            ab = s.get("bat_ab") or 0
            h = s.get("bat_hits") or 0
            d = s.get("bat_doubles") or 0
            tr = s.get("bat_triples") or 0
            hr = s.get("bat_home_runs") or 0
            rbi = s.get("bat_rbi") or 0
            runs = s.get("bat_runs") or 0
            bb = s.get("bat_walks") or 0
            k = s.get("bat_strike_outs") or 0
            sb = s.get("bat_stolen_bases") or 0
            hbp = s.get("bat_hbp") or 0
            sf = s.get("bat_sac_flys") or 0
            g = s.get("bat_games_played") or 0

            if g > 0 or ab > 0:
                avg = round(h / ab, 3) if ab else 0.0
                obp_d = ab + bb + hbp + sf
                obp = round((h + bb + hbp) / obp_d, 3) if obp_d else 0.0
                tb = h - d - tr - hr + 2 * d + 3 * tr + 4 * hr
                slg = round(tb / ab, 3) if ab else 0.0
                qualifies_bat = ab >= min_ab
                ab_k = round(ab / k, 2) if k else None
                hr_ab = round(hr / ab, 3) if ab else None
                batters.append(
                    {
                        "player_id": s["player_id"],
                        "name": f"{s['first_name']} {s['last_name']}",
                        "G": g,
                        "AB": ab,
                        "H": h,
                        "2B": d,
                        "3B": tr,
                        "HR": hr,
                        "RBI": rbi,
                        "R": runs,
                        "BB": bb,
                        "K": k,
                        "SB": sb,
                        "AVG": avg,
                        "OBP": obp,
                        "SLG": slg,
                        "OPS": round(obp + slg, 3),
                        "AB_K": ab_k,
                        "HR_AB": hr_ab,
                        "qualified": qualifies_bat,
                    }
                )

            outs = s.get("pitch_outs") or 0
            pg = s.get("pitch_games_played") or 0
            if pg > 0 or outs > 0:
                er = s.get("pitch_earned_runs") or 0
                ph = s.get("pitch_hits") or 0
                pbb = s.get("pitch_walks") or 0
                pk = s.get("pitch_strike_outs") or 0
                phr = s.get("pitch_home_runs") or 0
                w = s.get("pitch_wins") or 0
                l = s.get("pitch_losses") or 0
                sv = s.get("pitch_saves") or 0
                ip_f = outs / 3
                era = round((er * 27) / outs, 2) if outs else 0.0
                whip = round((pbb + ph) / ip_f, 2) if ip_f else 0.0
                bb9 = round((pbb * 27) / outs, 2) if outs else 0.0
                hr9 = round((phr * 27) / outs, 2) if outs else 0.0
                k9 = round((pk * 27) / outs, 2) if outs else 0.0
                gs = s.get("pitch_games_started") or 0
                ip_disp = f"{outs//3}.{outs%3}"
                qualifies_pit = outs >= min_outs
                pitchers.append(
                    {
                        "player_id": s["player_id"],
                        "name": f"{s['first_name']} {s['last_name']}",
                        "G": pg,
                        "GS": gs,
                        "W": w,
                        "L": l,
                        "SV": sv,
                        "IP": ip_disp,
                        "IP_val": ip_f,
                        "H": ph,
                        "ER": er,
                        "BB": pbb,
                        "K": pk,
                        "HR": phr,
                        "ERA": era,
                        "WHIP": whip,
                        "BB9": bb9,
                        "HR9": hr9,
                        "K9": k9,
                        "qualified": qualifies_pit,
                    }
                )

    # Attach injury status only for current season
    is_current_season = selected_season_id == current_season_id
    if selected_team_id and is_current_season:
        injured_map = _injured_player_ids(db, selected_team_id, league_id)
        for p in batters + pitchers:
            raw_days = injured_map.get(p["player_id"])
            p["injured"] = raw_days is not None
            p["injury_days"] = raw_days if raw_days else None
            p["returning"] = False
    else:
        for p in batters + pitchers:
            p["injured"] = False
            p["injury_days"] = None
            p["returning"] = False

    # Year label for selected season
    selected_year = next(
        (s["year"] for s in all_seasons if s["id"] == selected_season_id), None
    )

    ctx.update(
        {
            "all_teams": all_teams,
            "all_seasons": all_seasons,
            "selected_team_id": selected_team_id,
            "selected_season_id": selected_season_id,
            "selected_year": selected_year,
            "is_postseason": is_postseason,
            "team_games": team_games,
            "batters": batters,
            "pitchers": pitchers,
        }
    )
    return tab_response(request, htmx, "dashboard/partials/stats.html", ctx)


# ── Tab: Playoffs ──────────────────────────────────────────────────────────────


def _load_bracket(db, season_id: str, my_team_id: str | None) -> list:
    """Load full bracket state for template rendering."""
    ROUND_DEFS = [
        {"name": "Round 1", "series_names": ["1v8", "4v5", "2v7", "3v6"], "best_of": 5},
        {
            "name": "Semifinals",
            "series_names": ["[1,8]v[4,5]", "[2,7]v[3,6]"],
            "best_of": 7,
        },
        {"name": "Finals", "series_names": ["Finals"], "best_of": 7},
    ]
    # Map semifinal series name → which round-1 series feed into it
    _SEMI_FEEDERS = {
        "[1,8]v[4,5]": ("1v8", "4v5"),
        "[2,7]v[3,6]": ("2v7", "3v6"),
    }

    def _team_name(tid):
        tr = TeamRepository(db)
        return tr.get_city_mascot(team_id=tid)

    def load_series(series_name, best_of):
        por = PlayoffRepository(db)
        sid = por.get_series_id(season_id, series_name)
        if not sid:
            return {
                "name": series_name,
                "series_id": None,
                "best_of": best_of,
                "teams": [],
                "games_played": 0,
                "decided": False,
                "winner_id": None,
            }

        games = GameRepository(db).get_series_games(sid)

        team_ids = []
        seen = set()
        for g in games:
            for tid in (g["home_team_id"], g["away_team_id"]):
                if tid not in seen:
                    team_ids.append(tid)
                    seen.add(tid)

        # If this series has no games yet (prior round not fully complete),
        # try to show the known winner(s) from the feeder round-1 series.
        if not team_ids and series_name in _SEMI_FEEDERS:
            for feeder_name in _SEMI_FEEDERS[series_name]:
                feeder_sid = por.get_series_id(season_id, feeder_name)
                if feeder_sid:
                    w = por.get_series_winner(feeder_sid, 5)
                    if w and w not in seen:
                        team_ids.append(w)
                        seen.add(w)

        teams = []
        for tid in team_ids:
            wins = sum(1 for g in games if g["completed"] and g["winner_id"] == tid)
            teams.append(
                {
                    "team_id": tid,
                    "name": _team_name(tid),
                    "wins": wins,
                    "is_mine": tid == my_team_id,
                    "pending": len(games) == 0,
                }
            )

        wins_needed = {5: 3, 7: 4}[best_of]
        winner_id = next(
            (t["team_id"] for t in teams if t["wins"] >= wins_needed), None
        )
        games_played = sum(1 for g in games if g["completed"])
        completed_games = [
            {
                "id": g["id"],
                "winner_id": g["winner_id"],
                "home_score": g["home_score"],
                "away_score": g["away_score"],
            }
            for g in games
            if g["completed"]
        ]

        return {
            "name": series_name,
            "series_id": sid,
            "best_of": best_of,
            "wins_needed": wins_needed,
            "teams": teams,
            "games_played": games_played,
            "completed_games": completed_games,
            "decided": winner_id is not None,
            "winner_id": winner_id,
        }

    rounds = []
    for rd in ROUND_DEFS:
        series_list = [load_series(sn, rd["best_of"]) for sn in rd["series_names"]]
        rounds.append(
            {
                "name": rd["name"],
                "best_of": rd["best_of"],
                "series": series_list,
                "decided": all(s["decided"] for s in series_list),
            }
        )
    return rounds


@router.get("/leagues/{league_id}/playoffs", response_class=HTMLResponse)
def playoffs(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    ctx = _shell_ctx(request, db, gm, league_id, "playoffs", user)

    season_id = ctx["season_id"]
    my_team_id = gm["team_id"]

    bracket = _load_bracket(db, season_id, my_team_id) if season_id else []
    champion = None
    if bracket and bracket[-1]["decided"]:
        finals = bracket[-1]["series"][0]
        champion = next(
            (t for t in finals["teams"] if t["team_id"] == finals["winner_id"]), None
        )

    ctx.update(
        {
            "bracket": bracket,
            "champion": champion,
            "my_team_id": my_team_id,
        }
    )
    return tab_response(request, htmx, "dashboard/partials/playoffs.html", ctx)


@router.post("/leagues/{league_id}/playoffs/sim")
def sim_playoff_route(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
    mode: str = "game",
):
    result = sim_playoff(league_id, db, mode=mode)
    lr = LeagueRepository(db)
    result["league_state"] = lr.get_state(league_id)
    return JSONResponse(result)


# ── Game detail ────────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/games/{game_id}/panel", response_class=HTMLResponse)
def game_panel(
    request: Request,
    league_id: str,
    game_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    my_team_id = gm["team_id"]

    game_repo = GameRepository(db)
    pgs_repo = PlayerGameRepository(db)

    game = game_repo.get_with_teams(game_id)
    if not game:
        return HTMLResponse("Game not found", status_code=404)

    # Box score
    bat_rows = pgs_repo.get_batting_box_score(game_id)
    pit_rows = pgs_repo.get_pitching_box_score(game_id)

    def fmt_ip(outs):
        return f"{outs//3}.{outs%3}"

    home_bat = [r for r in bat_rows if r["team_id"] == game["home_team_id"]]
    away_bat = [r for r in bat_rows if r["team_id"] == game["away_team_id"]]
    home_pit = [r for r in pit_rows if r["team_id"] == game["home_team_id"]]
    away_pit = [r for r in pit_rows if r["team_id"] == game["away_team_id"]]
    for p in home_pit + away_pit:
        p["IP"] = fmt_ip(p["outs"] or 0)

    # Event log
    events_out = []
    for ed in game_repo.get_events(game_id):
        if ed.get("detail"):
            try:
                ed["detail_parsed"] = json.loads(ed["detail"])
            except Exception:
                ed["detail_parsed"] = None
        else:
            ed["detail_parsed"] = None
        events_out.append(ed)

    ctx = _shell_ctx(request, db, gm, league_id, user)
    ctx.update(
        {
            "game": game,
            "home_bat": home_bat,
            "away_bat": away_bat,
            "home_pit": home_pit,
            "away_pit": away_pit,
            "events": events_out,
            "my_team_id": my_team_id,
            "fmt_ip": fmt_ip,
        }
    )
    return templates.TemplateResponse(
        request=request, name="dashboard/partials/game_panel_content.html", context=ctx
    )


# ── Season Summary ─────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/season-summary", response_class=HTMLResponse)
def season_summary(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
    season_id: str | None = None,
):
    ctx = _shell_ctx(request, db, gm, league_id, user)
    my_team_id = gm["team_id"] if gm else None

    season_repo = SeasonRepository(db)
    series_repo = SeriesRepository(db)
    tg_repo = TeamGameRepository(db)
    game_repo = GameRepository(db)
    pss_repo = PlayerSeasonStatsRepository(db)

    # Use explicit season_id (from history link) or fall back to last season with series
    if not season_id:
        season_id = season_repo.get_last_with_series(league_id) or ctx["season_id"]

    # My team record
    my_record = None
    if my_team_id and season_id:
        my_record = tg_repo.get_team_wl(my_team_id, season_id)

    # Champion
    champion = None
    if season_id:
        champ = series_repo.get_champion(season_id)
        if champ:
            champion = {
                "team_id": champ["team_id"],
                "name": f"{champ['city']} {champ['mascot']}",
                "is_mine": champ["team_id"] == my_team_id,
            }

    # My playoff result
    my_playoff_result = None
    if my_team_id and season_id:
        my_playoff_result = series_repo.get_team_playoff_result(my_team_id, season_id)

    # Stat leaders — compute qualification thresholds from actual games played
    bat_leader = pit_leader = None
    if season_id:
        games_total = game_repo.get_completed_regular_season_count(season_id)
        num_teams = season_repo.get_team_count(season_id) or 30
        games_per_team = (games_total * 2) / num_teams if num_teams else 0
        min_ab = int(3.1 * games_per_team)
        min_outs = int(3 * games_per_team)

        br = pss_repo.get_batting_leader(league_id, season_id, min_ab)
        if br:
            bat_leader = {
                "name": f"{br['first_name']} {br['last_name']}",
                "team": f"{br['city']} {br['mascot']}",
                "stat": f"{br['avg']:.3f}",
                "label": "AVG",
            }

        pr = pss_repo.get_pitching_leader(league_id, season_id, min_outs)
        if pr:
            pit_leader = {
                "name": f"{pr['first_name']} {pr['last_name']}",
                "team": f"{pr['city']} {pr['mascot']}",
                "stat": f"{pr['era']:.2f}",
                "label": "ERA",
            }

    # Season year
    season_year = None
    if season_id:
        s = season_repo.get_season(season_id)
        season_year = s["year"] if s else None

    ctx.update(
        {
            "my_record": my_record,
            "champion": champion,
            "my_playoff_result": my_playoff_result,
            "bat_leader": bat_leader,
            "pit_leader": pit_leader,
            "season_year": season_year,
            "my_team_name": ctx.get("team_name", ""),
        }
    )
    return tab_response(request, htmx, "dashboard/partials/season_summary.html", ctx)


@router.get("/leagues/{league_id}/retirement", response_class=HTMLResponse)
def retirement(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    ctx = _shell_ctx(request, db, gm, league_id, user)
    my_team_id = gm["team_id"] if gm else None

    season_repo = SeasonRepository(db)
    current_season_id = season_repo.get_current_id_for_league(league_id)

    # Retirements happened in the season just before the current one
    prev_season = None
    if current_season_id:
        current_year = (season_repo.get_season(current_season_id) or {}).get("year")
        if current_year:
            prev_season = season_repo.get_by_league_and_year(
                league_id, current_year - 1
            )

    prev_season_id = prev_season["id"] if prev_season else None
    player_repo = PlayerRepository(db)
    retired_players = []
    if prev_season_id:
        rows = player_repo.get_retired_players_season_stats(
            my_team_id, league_id, prev_season_id
        )

        for r in rows:
            r = dict(r)
            ab = r.get("bat_ab") or 0
            hits = r.get("bat_hits") or 0
            bb = r.get("bat_walks") or 0
            outs = r.get("pitch_outs") or 0
            er = r.get("pitch_earned_runs") or 0
            pk = r.get("pitch_walks") or 0
            ph = r.get("pitch_hits") or 0
            r["has_bat_stats"] = ab > 0
            r["has_pit_stats"] = outs > 0
            # is_pitcher: used for games column; show pitching if outs dominate or no AB
            r["is_pitcher"] = outs > 0 and (ab == 0 or outs / 3 >= ab / 10)
            r["avg"] = f"{hits / ab:.3f}" if ab >= 1 else "—"
            r["obp"] = f"{(hits + bb) / (ab + bb):.3f}" if (ab + bb) >= 1 else "—"
            r["era"] = f"{(er * 27) / outs:.2f}" if outs >= 1 else "—"
            r["ip"] = f"{outs // 3}.{outs % 3}" if outs >= 1 else "0.0"
            r["whip"] = f"{(pk + ph) / (outs / 3):.2f}" if outs >= 1 else "—"
            retired_players.append(r)

    ctx.update({"retired_players": retired_players, "my_team_id": my_team_id})
    return tab_response(request, htmx, "dashboard/partials/retirement.html", ctx)


@router.post("/leagues/{league_id}/offseason/begin")
def begin_offseason(
    league_id: str,
    db: DB,
    gm: GM,
):
    try:
        result = run_offseason(league_id, db)
        return JSONResponse({"ok": True, **result})
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": str(e), "detail": traceback.format_exc()},
            status_code=500,
        )


# ── History ─────────────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/history", response_class=HTMLResponse)
def history(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    ctx = _shell_ctx(request, db, gm, league_id, user)
    my_team_id = gm["team_id"] if gm else None

    season_repo = SeasonRepository(db)
    series_repo = SeriesRepository(db)
    tg_repo = TeamGameRepository(db)

    seasons = season_repo.get_seasons_for_league(league_id)

    history_rows = []
    for s in seasons:
        champ = series_repo.get_champion(s["id"])
        champion_name = f"{champ['city']} {champ['mascot']}" if champ else None

        my_w = my_l = None
        if my_team_id:
            wl = tg_repo.get_team_wl(my_team_id, s["id"])
            if wl:
                my_w, my_l = wl["w"], wl["l"]

        history_rows.append(
            {
                "season_id": s["id"],
                "year": s["year"],
                "name": s["name"],
                "champion": champion_name,
                "my_w": my_w,
                "my_l": my_l,
            }
        )

    ctx["history_rows"] = history_rows
    return tab_response(request, htmx, "dashboard/partials/history.html", ctx)


# ── Player panel (slide-in) ────────────────────────────────────────────────────


@router.get(
    "/leagues/{league_id}/players/{player_id}/panel", response_class=HTMLResponse
)
def player_panel(
    request: Request,
    league_id: str,
    player_id: str,
    db: DB,
    user: User,
    gm: GM,
    compare: str | None = None,
):
    player_repo = PlayerRepository(db)
    status_repo = PlayerStatusRepository(db)
    energy_repo = PlayerEnergyRepository(db, league_id)
    inj_repo = InjuryRepository(db, league_id)
    team_repo = TeamRepository(db)
    season_repo = SeasonRepository(db)
    pss_repo = PlayerSeasonStatsRepository(db)

    league_row = LeagueRepository(db).get_by_id(league_id)
    _current_date: date | None = None
    if league_row:
        _season_id = season_repo.get_current_id_for_league(league_id)
        _date_str = _current_league_date(db, _season_id, league_row.get("state", ""))
        if _date_str:
            try:
                _current_date = date.fromisoformat(_date_str)
            except ValueError:
                pass

    def _load(pid: str) -> dict | None:
        p = player_repo.get_with_skills(pid)
        if not p:
            return None

        status = status_repo.get_status(pid) or "unassigned"
        en = (
            energy_repo.get_with_recovery(pid, _current_date, p.get("durability", 50))
            if _current_date
            else energy_repo.get(pid)
        )
        inj_log = inj_repo.get_injury_log(pid)
        team = team_repo.get_for_player(pid)

        grades = player_row_to_grades(p, p, status)
        ratings = _compute_ratings(p, p.get("throws", "R"))

        # Season stats — use last season with actual games so draft/offseason state
        # doesn't accidentally point at the upcoming empty season
        _last_season = season_repo.get_last_with_completed_games(league_id)
        current_season_id = _last_season["id"] if _last_season else None
        pitch_stats = None
        bat_stats = None
        if current_season_id:
            stats_row = pss_repo.get_player_season(pid, current_season_id)
            if stats_row:
                s = stats_row
                if s.get("pitch_games_played", 0) > 0:
                    outs = s.get("pitch_outs", 0) or 0
                    ip = outs // 3 + (outs % 3) / 10
                    er = s.get("pitch_earned_runs", 0) or 0
                    era = round((er * 27) / outs, 2) if outs > 0 else 0.0
                    walks = s.get("pitch_walks", 0) or 0
                    hits = s.get("pitch_hits", 0) or 0
                    whip = round((walks + hits) / (outs / 3), 2) if outs > 0 else 0.0
                    pitch_stats = {
                        "G": s.get("pitch_games_played", 0),
                        "GS": s.get("pitch_games_started", 0),
                        "W": s.get("pitch_wins", 0),
                        "L": s.get("pitch_losses", 0),
                        "SV": s.get("pitch_saves", 0),
                        "IP": f"{outs // 3}.{outs % 3}",
                        "H": hits,
                        "ER": er,
                        "BB": walks,
                        "K": s.get("pitch_strike_outs", 0),
                        "ERA": era,
                        "WHIP": whip,
                    }
                if s.get("bat_games_played", 0) > 0:
                    ab = s.get("bat_ab", 0) or 0
                    hits = s.get("bat_hits", 0) or 0
                    bb = s.get("bat_walks", 0) or 0
                    hbp = s.get("bat_hbp", 0) or 0
                    sf = s.get("bat_sac_flys", 0) or 0
                    avg = round(hits / ab, 3) if ab > 0 else 0.0
                    obp_denom = ab + bb + hbp + sf
                    obp = (
                        round((hits + bb + hbp) / obp_denom, 3)
                        if obp_denom > 0
                        else 0.0
                    )
                    tb = (
                        hits
                        - (s.get("bat_doubles", 0) or 0)
                        - (s.get("bat_triples", 0) or 0)
                        - (s.get("bat_home_runs", 0) or 0)
                        + 2 * (s.get("bat_doubles", 0) or 0)
                        + 3 * (s.get("bat_triples", 0) or 0)
                        + 4 * (s.get("bat_home_runs", 0) or 0)
                    )
                    slg = round(tb / ab, 3) if ab > 0 else 0.0
                    bat_stats = {
                        "G": s.get("bat_games_played", 0),
                        "AB": ab,
                        "H": hits,
                        "2B": s.get("bat_doubles", 0),
                        "3B": s.get("bat_triples", 0),
                        "HR": s.get("bat_home_runs", 0),
                        "RBI": s.get("bat_rbi", 0),
                        "R": s.get("bat_runs", 0),
                        "BB": bb,
                        "K": s.get("bat_strike_outs", 0),
                        "SB": s.get("bat_stolen_bases", 0),
                        "AVG": avg,
                        "OBP": obp,
                        "SLG": slg,
                        "OPS": round(obp + slg, 3),
                    }

        # Overall: prospect rating for undrafted, position-aware rating for rostered
        if status in ("prospect", "unassigned", "free_agent"):
            overall_grade = (
                skill_to_grade(ratings.get("prospect")) if ratings else grades.overall
            )
        elif grades.player_type == "pitcher":
            # Pitchers: best of SP/RP rating — overall_player is offense-based and useless
            best_p = max(ratings.get("sp", 0), ratings.get("rp", 0)) if ratings else 0
            overall_grade = skill_to_grade(best_p) if best_p else grades.overall
        else:
            overall_grade = (
                skill_to_grade(ratings.get("overall_player"))
                if ratings
                else grades.overall
            )

        grade_map = _ratings_to_grade_map(grades, p, ratings)

        # Best defensive grade for card display
        best_def_grade = skill_to_grade(ratings.get("best_def")) if ratings else "%s"
        best_def_label = ratings.get("best_def_label", "DEF") if ratings else "DEF"

        energy = None
        if grades.player_type != "pitcher":
            energy = {
                "current": round(en.current_energy * 100),
                "max": round(en.max_energy * 100),
                "consecutive_days": en.consecutive_days,
                "last_game_date": en.last_game_date,
                "season_games_played": en.season_games_played,
            }
        else:
            ps_repo = PitcherStateRepository(db, league_id)
            ps = (
                ps_repo.get_with_recovery(pid, _current_date, p.get("recovery", 50))
                if _current_date
                else ps_repo.get(pid)
            )
            if ps:
                days_rest = (
                    (_current_date - ps.last_game_date).days - 1
                    if _current_date and ps.last_game_date
                    else None
                )
                energy = {
                    "current": round(ps.current_energy * 100),
                    "max": round(ps.max_energy * 100),
                    "consecutive_days": ps.consecutive_days,
                    "last_game_date": ps.last_game_date,
                    "last_pitch_count": ps.last_pitch_count,
                    "season_games_played": None,
                    "days_rest": days_rest,
                }

        # Injury status
        injury = inj_repo.get(pid)
        raw_injury = injury.games_remaining if injury and injury.is_active else None

        return {
            **grades.model_dump(),
            "player_id": pid,
            "team_city": team["city"] if team else "—",
            "team_mascot": team["mascot"] if team else "",
            "grades": grade_map,
            "overall_grade": overall_grade,
            "best_def_grade": best_def_grade,
            "best_def_label": best_def_label,
            "energy": energy,
            "injury_log": inj_log,
            "pitch_stats": pitch_stats,
            "bat_stats": bat_stats,
            "injured": raw_injury is not None,
            "games_remaining": raw_injury,
            "returning": False,
        }

    ctx = _shell_ctx(request, db, gm, league_id, user)
    ctx["player"] = _load(player_id)
    ctx["compare_player"] = _load(compare) if compare else None
    return templates.TemplateResponse(
        request, "dashboard/partials/player_panel.html", ctx
    )


@router.get(
    "/leagues/{league_id}/players/{player_id}/career", response_class=HTMLResponse
)
def player_career(
    request: Request,
    league_id: str,
    player_id: str,
    db: DB,
    user: User,
    gm: GM,
    compare: str | None = None,
):
    player_repo = PlayerRepository(db)
    # inj_repo = InjuryRepository(db, league_id)

    def _load_career(pid: str) -> dict | None:
        p = player_repo.get_with_skills(pid)
        if not p:
            return None

        status = PlayerStatusRepository(db).get_status(pid) or "unassigned"
        grades = player_row_to_grades(p, p, status)
        ratings = _compute_ratings(p, p.get("throws", "R"))
        is_pitcher = grades.player_type == "pitcher"

        # Current ratings grouped into sections
        _sections = [
            (
                "Pitching",
                [
                    ("strikes", "Stuff"),
                    ("accuracy", "Control"),
                    ("stamina", "Stamina"),
                    ("recovery", "Recovery"),
                    ("ground_balls", "Ground Balls"),
                ],
            ),
            (
                "Hitting",
                [
                    ("contact", "Contact"),
                    ("power", "Power"),
                    ("eye", "Eye"),
                    ("base_running", "Baserunning"),
                    ("bunting", "Bunting"),
                ],
            ),
            (
                "Defense",
                [
                    ("catching", "Catching"),
                    ("infield", "Infield"),
                    ("outfield", "Outfield"),
                    ("arm", "Arm"),
                ],
            ),
            (
                "General",
                [
                    ("speed", "Speed"),
                    ("clutch", "Clutch"),
                    ("durability", "Durability"),
                ],
            ),
        ]
        rating_sections = [
            {
                "section": section,
                "skills": [
                    {"label": label, "grade": skill_to_grade(p[key])}
                    for key, label in skills
                    if p.get(key) is not None
                ],
            }
            for section, skills in _sections
        ]

        # Career stats — regular season + playoffs, newest first; playoffs above reg season within year
        stat_rows = player_repo.get_career_stats(pid)

        pitching_seasons = []
        batting_seasons = []
        p_totals: dict = {}
        b_totals: dict = {}
        pp_totals: dict = {}
        pb_totals: dict = {}

        for r in [dict(x) for x in stat_rows]:
            yr = r["year"]
            is_post = bool(r.get("is_postseason"))
            team = f"{r['team_city']} {r['team_mascot']}"

            if (r.get("pitch_games_played") or 0) > 0:
                outs = r.get("pitch_outs", 0) or 0
                ip = outs / 3.0
                er = r.get("pitch_earned_runs", 0) or 0
                hits = r.get("pitch_hits", 0) or 0
                bb = r.get("pitch_walks", 0) or 0
                era = round(er / ip * 9, 2) if ip > 0 else 0.0
                whip = round((hits + bb) / ip, 2) if ip > 0 else 0.0
                prow = {
                    "year": yr,
                    "team": team,
                    "postseason": is_post,
                    "G": r.get("pitch_games_played", 0),
                    "GS": r.get("pitch_games_started", 0),
                    "W": r.get("pitch_wins", 0),
                    "L": r.get("pitch_losses", 0),
                    "SV": r.get("pitch_saves", 0),
                    "IP": f"{outs // 3}.{outs % 3}",
                    "H": hits,
                    "ER": er,
                    "BB": bb,
                    "K": r.get("pitch_strike_outs", 0),
                    "HR": r.get("pitch_home_runs", 0),
                    "ERA": era,
                    "WHIP": whip,
                }
                pitching_seasons.append(prow)
                t = p_totals if not is_post else pp_totals
                for k in ("G", "GS", "W", "L", "SV", "H", "ER", "BB", "K", "HR"):
                    t[k] = t.get(k, 0) + prow[k]
                t["_outs"] = t.get("_outs", 0) + outs

            if (r.get("bat_games_played") or 0) > 0:
                ab = r.get("bat_ab", 0) or 0
                h = r.get("bat_hits", 0) or 0
                bb = r.get("bat_walks", 0) or 0
                hbp = r.get("bat_hbp", 0) or 0
                sf = r.get("bat_sac_flys", 0) or 0
                dbl = r.get("bat_doubles", 0) or 0
                trp = r.get("bat_triples", 0) or 0
                hr = r.get("bat_home_runs", 0) or 0
                slg_num = h + dbl + 2 * trp + 3 * hr
                obp_d = ab + bb + hbp + sf
                brow = {
                    "year": yr,
                    "team": team,
                    "postseason": is_post,
                    "G": r.get("bat_games_played", 0),
                    "AB": ab,
                    "H": h,
                    "2B": dbl,
                    "3B": trp,
                    "HR": hr,
                    "RBI": r.get("bat_rbi", 0) or 0,
                    "R": r.get("bat_runs", 0) or 0,
                    "BB": bb,
                    "K": r.get("bat_strike_outs", 0) or 0,
                    "SB": r.get("bat_stolen_bases", 0) or 0,
                    "AVG": round(h / ab, 3) if ab > 0 else 0.0,
                    "OBP": round((h + bb + hbp) / obp_d, 3) if obp_d > 0 else 0.0,
                    "SLG": round(slg_num / ab, 3) if ab > 0 else 0.0,
                    "OPS": round(
                        ((h + bb + hbp) / obp_d if obp_d > 0 else 0)
                        + (slg_num / ab if ab > 0 else 0),
                        3,
                    ),
                }
                batting_seasons.append(brow)
                t = b_totals if not is_post else pb_totals
                for k in (
                    "G",
                    "AB",
                    "H",
                    "2B",
                    "3B",
                    "HR",
                    "RBI",
                    "R",
                    "BB",
                    "K",
                    "SB",
                ):
                    t[k] = t.get(k, 0) + brow[k]
                t["_ab"] = t.get("_ab", 0) + ab
                t["_h"] = t.get("_h", 0) + h
                t["_bb"] = t.get("_bb", 0) + bb
                t["_hbp"] = t.get("_hbp", 0) + hbp
                t["_sf"] = t.get("_sf", 0) + sf
                t["_slg_num"] = t.get("_slg_num", 0) + slg_num

        def _pitch_totals(d: dict) -> dict | None:
            if not d:
                return None
            outs = d.pop("_outs", 0)
            ip = outs / 3.0
            return {
                **d,
                "IP": f"{outs // 3}.{outs % 3}",
                "ERA": round(d.get("ER", 0) / ip * 9, 2) if ip > 0 else 0.0,
                "WHIP": (
                    round((d.get("H", 0) + d.get("BB", 0)) / ip, 2) if ip > 0 else 0.0
                ),
            }

        def _bat_totals(d: dict) -> dict | None:
            if not d:
                return None
            ab = d.pop("_ab", 0)
            h = d.pop("_h", 0)
            bb = d.pop("_bb", 0)
            hbp = d.pop("_hbp", 0)
            sf = d.pop("_sf", 0)
            slg_num = d.pop("_slg_num", 0)
            obp_d = ab + bb + hbp + sf
            obp = round((h + bb + hbp) / obp_d, 3) if obp_d > 0 else 0.0
            slg = round(slg_num / ab, 3) if ab > 0 else 0.0
            return {
                **d,
                "AVG": round(h / ab, 3) if ab > 0 else 0.0,
                "OBP": obp,
                "SLG": slg,
                "OPS": round(obp + slg, 3),
            }

        pitching_totals = _pitch_totals(p_totals)
        pitching_playoff_totals = _pitch_totals(pp_totals)
        batting_totals = _bat_totals(b_totals)
        batting_playoff_totals = _bat_totals(pb_totals)

        # Injuries grouped by season year
        inj_repo = InjuryRepository(db)
        all_inj = inj_repo.get_injuries_by_year(pid)
        injuries_by_year: dict[str, list] = {}
        for r in all_inj:
            yr = str(r["season_year"]) if r["season_year"] else "Pre-season"
            injuries_by_year.setdefault(yr, []).append(dict(r))

        overall_grade = grades.overall
        if status in ("prospect", "unassigned", "free_agent"):
            overall_grade = (
                skill_to_grade(ratings.get("prospect")) if ratings else grades.overall
            )
        elif is_pitcher:
            best_p = max(ratings.get("sp", 0), ratings.get("rp", 0)) if ratings else 0
            overall_grade = skill_to_grade(best_p) if best_p else grades.overall
        else:
            overall_grade = (
                skill_to_grade(ratings.get("overall_player"))
                if ratings
                else grades.overall
            )

        return {
            **grades.model_dump(),
            "player_id": pid,
            "overall_grade": overall_grade,
            "rating_sections": rating_sections,
            "pitching_seasons": pitching_seasons,
            "pitching_totals": pitching_totals,
            "pitching_playoff_totals": pitching_playoff_totals,
            "batting_seasons": batting_seasons,
            "batting_totals": batting_totals,
            "batting_playoff_totals": batting_playoff_totals,
            "injuries_by_year": injuries_by_year,
        }

    ctx = _shell_ctx(request, db, gm, league_id, user)
    ctx["player"] = _load_career(player_id)
    ctx["compare_player"] = _load_career(compare) if compare else None
    return templates.TemplateResponse(
        request, "dashboard/partials/player_career.html", ctx
    )


@router.get("/leagues/{league_id}/history/{year}/", response_class=HTMLResponse)
def history_season_detail(
    request: Request,
    league_id: str,
    year: int,
    db: DB,
    gm: GM,
):
    season = SeasonRepository(db).get_by_league_and_year(league_id, year)
    evaluation = (
        GMEvaluationRepository(db).get(gm["id"], season["id"]) if season else None
    )

    return templates.TemplateResponse(
        request,
        "history/season.html",
        {
            "league_id": league_id,
            "year": year,
            "season": season,
            "gm_evaluation": evaluation,
            "standings": [],
            "stat_leaders": {},
            "win_trend": [],
        },
    )
