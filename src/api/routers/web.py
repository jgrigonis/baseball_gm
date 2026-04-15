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

import uuid
import traceback

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.api.dependencies import DB, User, OptionalUser, GM, Commissioner, IsHTMX
from src.api.schemas import player_row_to_grades, skill_to_grade, BullpenSaveRequest
from src.api.services.league_start import start_league as _start
from src.db.repositories.draft_repo import DraftRepository
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.injury_repo import InjuryRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.lineup_preference_repo import LineupPreferenceRepository
from src.db.repositories.team_rotations_repo import TeamRotationsRepository
from src.db.repositories.user_repo import UserRepository
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_skills import PlayerSkills, SKILLS
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
        # Filter to valid skill keys only — DB rows include player_id, updated_at, etc.
        filtered = {k: v for k, v in skills.items() if k in SKILLS and v is not None}
        ps = PlayerSkills(filtered)
        ratings = PlayerEvaluator.rate_player(ps, throws or "R")
    except Exception:
        return {}

    if_rating = max(ratings.get("2b", 0), ratings.get("3b", 0), ratings.get("ss", 0))
    of_rating = max(ratings.get("lf", 0), ratings.get("cf", 0), ratings.get("rf", 0))
    c_rating = ratings.get("c", 0)
    b1_rating = ratings.get("1b", 0)

    best_def = max(if_rating, of_rating, c_rating, b1_rating)
    if best_def == c_rating and c_rating >= max(if_rating, of_rating, b1_rating):
        best_def_label = "CA"
    elif best_def == b1_rating and b1_rating >= max(if_rating, of_rating, c_rating):
        best_def_label = "1B"
    elif best_def == of_rating and of_rating >= max(if_rating, c_rating, b1_rating):
        best_def_label = "OF"
    else:
        best_def_label = "IF"

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

# moved to utils
# def _is_htmx(request: Request) -> bool:
#     return request.headers.get("HX-Request") == "true"


# def _resolve_user(db, token: str | None):
#     """Return the users row for a session cookie, or None."""
#     if not token:
#         return None
#     return db.execute(
#         "SELECT * FROM users WHERE session_token = %s", (token,)
#     ).fetchone()


# def _resolve_gm(db, user_id: str, league_id: str):
#     """Return the gms row for this user in this league, or None."""
#     return db.execute(
#         "SELECT * FROM gms WHERE user_id = %s AND league_id = %s",
#         (user_id, league_id),
#     ).fetchone()


def _injured_player_ids(db, team_id: str, league_id: str = "") -> dict:
    """Return dict of {player_id: games_remaining} for players on IL for a team."""
    return InjuryRepository(db, league_id).get_team_injuries(team_id)


def _games_remaining(db, season_id: str | None) -> int:
    """Return the number of unplayed games remaining in a season."""
    return GameRepository(db).games_remaining(season_id)
    # if not season_id:
    #     return 0
    # row = db.execute(
    #     "SELECT COUNT(*) FROM games WHERE season_id = %s AND completed = 0",
    #     (season_id,),
    # ).fetchone()
    # return row["count"] if row else 0


# This is used code in that monster return in old _shell_ctx
# def _draft_is_complete(db, league_id: str) -> bool:
#     row = db.execute(
#         """SELECT d.state FROM drafts d
#            JOIN league_seasons ls ON ls.season_id = d.season_id
#            JOIN seasons s ON s.id = ls.season_id
#            WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
#         (league_id,),
#     ).fetchone()
#     return bool(row and row["state"] == "complete")

# moved to utils
# def _tab_visible(state: str, draft_complete: bool = False) -> list[str]:
#     if state == "lobby":
#         return []
#     if not draft_complete:
#         return [
#             "draft",
#             "roster",
#             "lineup",
#             "standings",
#             "leaders",
#             "stats",
#             "strategy",
#         ]
#     post = ["roster", "lineup", "schedule", "standings", "leaders", "stats", "strategy"]
#     if state not in ("season", "playoffs", "preseason", "offseason"):
#         post.remove("schedule")
#     if state in ("playoffs", "offseason"):
#         post.append("playoffs")
#     post.append("draft")  # draft results at far right
#     return post


# def _current_league_date(db, season_id: str | None, state: str) -> str | None:
#     """Return the next unplayed game date, or last played date if season is over."""
#     if not season_id or state not in ("preseason", "season", "playoffs"):
#         return None
#     # Next unplayed regular season game
#     row = db.execute(
#         "SELECT game_date FROM games WHERE season_id = %s AND completed = 0 AND series_id IS NULL ORDER BY game_date ASC LIMIT 1",
#         (season_id,),
#     ).fetchone()
#     if row:
#         return row["game_date"]
#     # Playoffs: next unplayed playoff game
#     row = db.execute(
#         "SELECT game_date FROM games WHERE season_id = %s AND completed = 0 ORDER BY game_date ASC LIMIT 1",
#         (season_id,),
#     ).fetchone()
#     if row:
#         return row["game_date"]
#     # All done — last played date
#     row = db.execute(
#         "SELECT MAX(game_date) as d FROM games WHERE season_id = %s AND completed = 1",
#         (season_id,),
#     ).fetchone()
#     return row["d"] if row else None

# moved to utils
# def _shell_ctx(
#     request: Request,
#     db,
#     league_id: str,
#     user: dict,
#     gm: dict | None,
#     active_tab: str | None = None,
# ) -> dict:
#     league = db.execute("SELECT * FROM leagues WHERE id = %s", (league_id,)).fetchone()
#     team = None
#     if gm and gm["team_id"]:
#         team = db.execute(
#             "SELECT city, mascot FROM teams WHERE id = %s", (gm["team_id"],)
#         ).fetchone()

#     league_state_for_season = league["state"] if league else "lobby"

#     if league_state_for_season == "draft":
#         # During draft, show the last COMPLETED season for standings/schedule/etc.
#         # Year 2 is being drafted but has no games — year 1's data is what's useful.
#         season = db.execute(
#             """SELECT s.* FROM seasons s
#                JOIN league_seasons ls ON ls.season_id = s.id
#                WHERE ls.league_id = %s
#                  AND EXISTS (
#                    SELECT 1 FROM games g WHERE g.season_id = s.id AND g.completed = 1
#                  )
#                ORDER BY s.year DESC LIMIT 1""",
#             (league_id,),
#         ).fetchone()
#         # Fallback to newest if nothing completed yet (first ever draft)
#         if season is None:
#             season = db.execute(
#                 """SELECT s.* FROM seasons s
#                    JOIN league_seasons ls ON ls.season_id = s.id
#                    WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
#                 (league_id,),
#             ).fetchone()
#     elif league_state_for_season in ("playoffs", "offseason"):
#         # During playoffs/offseason, use the season that has series records
#         season = db.execute(
#             """SELECT s.* FROM seasons s
#                JOIN league_seasons ls ON ls.season_id = s.id
#                WHERE ls.league_id = %s
#                  AND EXISTS (
#                    SELECT 1 FROM series sr WHERE sr.season_id = s.id
#                  )
#                ORDER BY s.year DESC LIMIT 1""",
#             (league_id,),
#         ).fetchone()
#         # Fallback to newest if no series yet
#         if season is None:
#             season = db.execute(
#                 """SELECT s.* FROM seasons s
#                    JOIN league_seasons ls ON ls.season_id = s.id
#                    WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
#                 (league_id,),
#             ).fetchone()
#     else:
#         # season/preseason: show the newest season (current active season)
#         season = db.execute(
#             """SELECT s.* FROM seasons s
#                JOIN league_seasons ls ON ls.season_id = s.id
#                WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
#             (league_id,),
#         ).fetchone()

#     return {
#         "league_id": league_id,
#         "league_name": league["name"] if league else "—",
#         "league_state": league["state"] if league else "lobby",
#         "league_mode": league["mode"] if league else "blitz",
#         "join_code": league["join_code"] if league else "",
#         "num_teams": league["num_teams"] if league else 30,
#         "decision_window_sec": league["decision_window_sec"] if league else 120,
#         "draft_window_sec": league["draft_window_sec"] if league else 300,
#         "reentry_enabled": bool(league["reentry_enabled"]) if league else True,
#         "pace_control": league["pace_control"] if league else "timer",
#         "gm_id": gm["id"] if gm else None,
#         "gm_display_name": gm["display_name"] if gm else user["display_name"],
#         "team_id": gm["team_id"] if gm else None,
#         "team_name": f"{team['city']} {team['mascot']}" if team else None,
#         "is_commissioner": (league and gm and league["commissioner_gm_id"] == gm["id"]),
#         "active_tab": active_tab,
#         "visible_tabs": _tab_visible(
#             league["state"] if league else "lobby",
#             _draft_is_complete(db, league_id) if league else False,
#         ),
#         "season_id": season["id"] if season else None,
#         "current_date": _current_league_date(
#             db, season["id"] if season else None, league["state"] if league else "lobby"
#         ),
#         "season_name": season["name"] if season else None,
#         "draft_complete": _draft_is_complete(db, league_id) if league else False,
#         "games_remaining": _games_remaining(db, season["id"] if season else None),
#     }

# refactored away
# def _respond(request: Request, partial_template: str, ctx: dict) -> HTMLResponse:
#     """HTMX → return partial only. Direct nav → full shell with partial embedded."""
#     if _is_htmx(request):
#         return templates.TemplateResponse(request, partial_template, ctx)
#     ctx["tab_template"] = partial_template
#     return templates.TemplateResponse(request, "dashboard/shell.html", ctx)

# Trying to inject the is_htmx
# moved to utils
# def respond(request: Request, is_htmx: bool, partial_template: str, ctx: dict) -> HTMLResponse:
#     """HTMX → return partial only. Direct nav → full shell with partial embedded."""
#     if is_htmx:
#         return templates.TemplateResponse(request, partial_template, ctx)

#     ctx["tab_template"] = partial_template
#     return templates.TemplateResponse(request, "dashboard/shell.html", ctx)


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
    # Reuse existing session if the cookie is still valid
    # existing_token = request.cookies.get("gm_session")
    # if existing_token:
    #     existing = db.execute(
    #         "SELECT * FROM users WHERE session_token = %s", (existing_token,)
    #     ).fetchone()
    #     if existing:
    #         return RedirectResponse("/leagues/", status_code=302)
    if user:
        return RedirectResponse("/leagues/", status_code=302)

    token = uuid.uuid4().hex + uuid.uuid4().hex
    user_id = str(uuid.uuid4())
    user_repo = UserRepository(db)
    user_repo.insert_user(user_id, token, display_name or "Guest")
    # db.execute(
    #     "INSERT INTO users (id, session_token, display_name) VALUES (%s, %s, %s)",
    #     (user_id, token, display_name or "Guest"),
    # )
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


# This doesn't seem to do anything anyway, just a security hole
# @router.post("/auth/reclaim/{league_id}")
# def reclaim_league(
#     request: Request,
#     league_id: str,
#     db: DB,
#     gm_session: str | None = Cookie(default=None),
# ):
#     """
#     Reassign a league's gm.user_id to the current session's user.
#     Used when a guest has lost their cookie and wants to reconnect.
#     """
#     user = _resolve_user(db, gm_session)
#     if not user:
#         return RedirectResponse("/", status_code=302)

#     # Find the gm row for this league that has the same display name
#     gm = db.execute(
#         """SELECT g.id FROM gms g
#            JOIN users u ON u.id = g.user_id
#            WHERE g.league_id = %s AND u.display_name = %s AND g.is_ai = 0
#            LIMIT 1""",
#         (league_id, user["display_name"]),
#     ).fetchone()

#     if gm:
#         db.execute(
#             "UPDATE gms SET user_id = %s WHERE id = %s",
#             (user["id"], gm["id"]),
#         )
#         db.commit()

#     return RedirectResponse(f"/leagues/{league_id}/", status_code=302)


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
    # 1. Identity Reclaim (Auto-linking)
    # We still need this for now since we aren't doing 2FA/Logins yet,
    # but the dependency ensures 'user' is already valid.
    # Auto-reclaim: any gm row with same display_name but different user_id
    # gets reassigned to the current user. This handles the common case where
    # the browser cookie was cleared and a new guest identity was created.
    db.execute(
        """UPDATE gms SET user_id = %s
           WHERE is_ai = 0
             AND user_id != %s
             AND user_id IN (
               SELECT id FROM users WHERE display_name = %s
             )""",
        (user["id"], user["id"], user["display_name"]),
    )
    db.commit()

    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/")
    # db.execute(
    #     """UPDATE gms SET user_id = %s
    #        WHERE is_ai = 0
    #          AND user_id != %s
    #          AND user_id IN (
    #            SELECT id FROM users WHERE display_name = %s
    #          )""",
    #     (user["id"], user["id"], user["display_name"]),
    # )
    # db.commit()

    # 2. Fetch User's Leagues
    rows = db.execute(
        """SELECT l.id, l.name, l.state, l.mode, l.created_at 
           FROM leagues l
           JOIN gms g ON g.league_id = l.id
           WHERE g.user_id = %s AND g.is_ai = 0
           ORDER BY l.created_at DESC""",
        (user["id"],),
    ).fetchall()

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
    import random as _random, string as _string, uuid as _uuid

    league_id = str(_uuid.uuid4())
    gm_id = str(_uuid.uuid4())
    join_code = "".join(_random.choices(_string.ascii_uppercase + _string.digits, k=6))

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

    gm_repo.create_gm(
        gm_id=gm_id,
        league_id=league_id,
        user_id=user["id"],
        display_name=user["display_name"],
    )
    # 3. Update the League (Now the GM exists, so the commish ID is valid)
    gm_repo.set_commissioner(gm_id=gm_id, league_id=league_id)
    # db.execute(
    #     "UPDATE leagues SET commissioner_gm_id = %s WHERE id = %s", (gm_id, league_id)
    # )

    # # 2. Create the GM
    # db.execute(
    #     "INSERT INTO gms (id, league_id, user_id, display_name, is_ai) VALUES (%s, %s, %s, %s, 0)",
    #     (gm_id, league_id, user["id"], user["display_name"]),
    # )
    # # 3. Create GM Profile
    # db.execute("INSERT INTO gm_profiles (gm_id) VALUES (%s)", (gm_id,))

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
    # # Check if already a member
    # existing = db.execute(
    #     "SELECT id FROM gms WHERE league_id = %s AND user_id = %s",
    #     (league["id"], user["id"]),
    # ).fetchone()
    # if existing:
    #     return RedirectResponse(f"/leagues/{league['id']}/", status_code=302)

    # 3. Join the league using our clean GM creator
    gm_id = str(uuid.uuid4())
    # This repo method now handles the GM row AND the GM Profile automatically!
    gm_repo.create_gm(
        gm_id=gm_id,
        league_id=league["id"],
        user_id=user["id"],
        display_name=user["display_name"],
    )

    # db.execute(
    #     "INSERT INTO gms (id, league_id, user_id, display_name, is_ai) VALUES (%s, %s, %s, %s, 0)",
    #     (gm_id, league["id"], user["id"], user["display_name"]),
    # )
    # db.execute("INSERT INTO gm_profiles (gm_id) VALUES (%s)", (gm_id,))
    db.commit()

    return RedirectResponse(f"/leagues/{league['id']}/", status_code=302)


@router.get("/leagues/join", response_class=HTMLResponse)
def join_page(request: Request):
    return templates.TemplateResponse(request, "leagues/join.html", {})


# ── League actions ────────────────────────────────────────────────────────────


@router.post("/leagues/{league_id}/start")
def start_league(
    league_id: str,
    db: DB,
    _: Commissioner,
):
    try:
        _start(league_id, db)
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


# @router.post("/leagues/{league_id}/start")
# def start_league(
#     request: Request,
#     league_id: str,
#     db: DB,
#     gm_session: str | None = Cookie(default=None),
# ):
#     user = _resolve_user(db, gm_session)
#     if not user:
#         return RedirectResponse("/", status_code=302)

#     gm = _resolve_gm(db, user["id"], league_id)
#     if not gm:
#         return RedirectResponse(f"/leagues/{league_id}/", status_code=302)

#     league = db.execute("SELECT * FROM leagues WHERE id = %s", (league_id,)).fetchone()
#     if not league or league["commissioner_gm_id"] != gm["id"]:
#         return RedirectResponse(f"/leagues/{league_id}/", status_code=302)

#     from src.api.services.league_start import start_league as _start
#     import traceback

#     try:
#         _start(league_id, db)
#     except Exception:
#         # Surface the error as a plain response so we can see what went wrong
#         return HTMLResponse(
#             f"<pre style='font-family:monospace;padding:24px;background:#0c0f1a;color:#ef4444;'>"
#             f"Start league failed:\n\n{traceback.format_exc()}</pre>",
#             status_code=500,
#         )

#     return RedirectResponse(f"/leagues/{league_id}/", status_code=302)


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
    from fastapi.responses import JSONResponse

    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    # gm = _resolve_gm(db, user["id"], league_id)
    # if not gm:
    #     return JSONResponse({"detail": "Not a member of this league"}, status_code=403)

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


# ── Dashboard shell ────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):

    league = db.execute("SELECT * FROM leagues WHERE id = %s", (league_id,)).fetchone()
    if not league:
        return RedirectResponse("/leagues/")

    is_commish = league["commissioner_gm_id"] == gm["id"]

    state = league["state"]
    # Redirect logic
    if state == "draft":
        return RedirectResponse(f"/leagues/{league_id}/draft")
    if state in ("season", "playoffs"):
        return RedirectResponse(f"/leagues/{league_id}/standings")
    if state == "evaluation":
        # Simplified the season fetch for now to get you back to green
        return RedirectResponse(f"/leagues/{league_id}/history/1/")

    gms_in_league = db.execute(
        "SELECT * FROM gms WHERE league_id = %s", (league_id,)
    ).fetchall()

    # print(f"DEBUG: League Commish ID: {league['commissioner_gm_id']}")
    # print(f"DEBUG: My GM ID: {gm['id']}")
    # This boolean is what the Jinja template is looking for
    is_commish = league["commissioner_gm_id"] == gm["id"]

    context_drawer = {
        "league_id": league_id,
        "league_name": league["name"],
        "is_commissioner": bool(is_commish),
        "gms": list(gms_in_league),
        # "num_teams": league["num_teams"],
        "league_num_teams": league["num_teams"],  # Dual-mapping for safety
        "league_mode": league["mode"],
        "join_code": league.get("join_code"),
        "league_decision_window_sec": league["decision_window_sec"],
        "league_draft_window_sec": league["draft_window_sec"],
        "league_pace_control": league.get("pace_control", "manual"),
        "current_gm_id": str(gm["id"]),
    }

    # print("\n--- DEBUG: TEMPLATE CONTEXT ---")
    # for k, v in context_drawer.items():
    #     print(f"{k}: {v}")
    # print("-------------------------------\n")

    return templates.TemplateResponse(
        request=request, name="dashboard/lobby.html", context=context_drawer
    )
    # if state == "lobby":
    #     return RedirectResponse(f"/leagues/{league_id}/draft")
    # return _lobby(request, league_id, db, user, gm)
    # if state == "draft":
    #     return RedirectResponse(f"/leagues/{league_id}/draft")
    # if state in ("season", "playoffs"):
    #     return RedirectResponse(f"/leagues/{league_id}/standings")
    # if state == "evaluation":
    #     season = db.execute(
    #         """SELECT s.year FROM seasons s JOIN league_seasons ls
    #            ON ls.season_id = s.id WHERE ls.league_id = %s
    #            ORDER BY s.year DESC LIMIT 1""",
    #         (league_id,),
    #     ).fetchone()
    #     year = season["year"] if season else 1
    #     return RedirectResponse(f"/leagues/{league_id}/history/{year}/")
    # return templates.TemplateResponse(
    #     request=request,
    #     name="dashboard/lobby.html",
    #     context={
    #         "league_id": str(league_id),
    #         "league_name": str(league["name"]),
    #         "is_commissioner": bool(is_commish),
    #         "gms": list(gms_in_league),
    #     }
    # )
    # "dashboard/lobby.html", {
    # "request": request,
    # "league_name": "Testing Connection",
    # "is_commissioner": True, # Hardcode to see if the button appears!
    # "gms": [],
    # "num_teams": 0
    # "request": request,
    # "league_id": str(league_id),
    # "league_name": str(league["name"]),
    # "league_mode": league["mode"],
    # "join_code": league.get("join_code"),
    # "num_teams": league["num_teams"],
    # "decision_window_sec": league["decision_window_sec"],
    # "draft_window_sec": league["draft_window_sec"],
    # "reentry_enabled": league.get("reentry_enabled", False),
    # "pace_control": league.get("pace_control", "manual"),
    # "gms": list(gms_in_league),
    # "current_gm_id": str(gm["id"]),
    # "is_commissioner": bool(is_commish),


def _lobby(request, league_id, db, user, gm):
    league = db.execute("SELECT * FROM leagues WHERE id = %s", (league_id,)).fetchone()
    gms = db.execute(
        """SELECT g.id, g.display_name, g.is_ai, g.is_away, g.team_id,
                  t.city, t.mascot
           FROM gms g LEFT JOIN teams t ON t.id = g.team_id
           WHERE g.league_id = %s ORDER BY g.created_at""",
        (league_id,),
    ).fetchall()
    return templates.TemplateResponse(
        request,
        "dashboard/lobby.html",
        {
            "league_id": league_id,
            "league_name": league["name"],
            "league_state": "lobby",
            "join_code": league["join_code"],
            "num_teams": league["num_teams"],
            "decision_window_sec": league["decision_window_sec"],
            "draft_window_sec": (dict(league).get("draft_window_sec") or 300),
            "reentry_enabled": bool(league["reentry_enabled"]),
            "pace_control": league["pace_control"],
            "league_mode": league["mode"],
            "gm_display_name": gm["display_name"] if gm else user["display_name"],
            "current_gm_id": gm["id"] if gm else None,
            "is_commissioner": gm and league["commissioner_gm_id"] == gm["id"],
            "draft_complete": False,
            "visible_tabs": [],
            "gms": [dict(r) for r in gms],
        },
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
    # gm_session: str | None = Cookie(default=None),
):
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/")

    # gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, gm, league_id, "draft", user)

    draft_repo = DraftRepository(db)
    draft = draft_repo.get_current_for_league(league_id)

    if draft:
        picked_ids = draft_repo.get_picked_ids(draft["id"])
        all_players = draft_repo.get_prospects(league_id)

        board = []
        for row in all_players:
            if row["id"] in picked_ids:
                continue
            skills_row = db.execute(
                "SELECT * FROM player_skills WHERE player_id = %s", (row["id"],)
            ).fetchone()
            skills = dict(skills_row) if skills_row else {}
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
        roster_rows = db.execute(
            """SELECT p.*, ps.status
               FROM players p
               JOIN team_players tp ON tp.player_id = p.id AND tp.team_id = %s
               JOIN player_status ps ON ps.player_id = p.id
               ORDER BY ps.status, p.last_name""",
            (gm["team_id"],),
        ).fetchall()
        for row in roster_rows:
            d = dict(row)
            skills_row = db.execute(
                "SELECT * FROM player_skills WHERE player_id = %s", (d["id"],)
            ).fetchone()
            skills = dict(skills_row) if skills_row else {}
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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/", status_code=302)

    # gm = _resolve_gm(db, user["id"], league_id)
    # if not gm:
    #     return RedirectResponse(f"/leagues/{league_id}/draft", status_code=302)

    draft = DraftRepository(db).get_current_for_league(league_id)

    if not draft:
        return RedirectResponse(f"/leagues/{league_id}/draft", status_code=302)

    # If already complete, just go to results
    if draft["state"] == "complete":
        return RedirectResponse(f"/leagues/{league_id}/draft/results", status_code=302)

    import traceback

    try:
        from src.api.services.draft_execute import execute_blitz_draft

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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/")

    # gm = _resolve_gm(db, user["id"], league_id)
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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return HTMLResponse("Unauthorized", status_code=401)

    # gm = _resolve_gm(db, user["id"], league_id)
    # if not gm or not gm["team_id"]:
    #     return HTMLResponse("No team", status_code=400)

    # Read JSON body
    import asyncio

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
    from fastapi.responses import JSONResponse

    # import asyncio

    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    # gm = _resolve_gm(db, user["id"], league_id)
    # if not gm or not gm["team_id"]:
    #     return JSONResponse({"detail": "No team"}, status_code=400)

    team_id = gm["team_id"]

    # Parse body synchronously via stored body
    body = None
    try:
        import asyncio as _asyncio

        loop = _asyncio.new_event_loop()
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

    # Verify all submitted players belong to this team
    team_player_ids = {
        r["player_id"]
        for r in db.execute(
            "SELECT player_id FROM team_players WHERE team_id = %s", (team_id,)
        ).fetchall()
    }
    for pid in forty_man_ids:
        if pid not in team_player_ids:
            return JSONResponse(
                {"detail": f"Player {pid} not on this team"}, status_code=422
            )

    forty_set = set(forty_man_ids)

    # Update statuses
    for pid in team_player_ids:
        new_status = "40man" if pid in forty_set else "minors"
        existing = db.execute(
            "SELECT status FROM player_status WHERE player_id = %s", (pid,)
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE player_status SET status = %s WHERE player_id = %s",
                (new_status, pid),
            )
        else:
            db.execute(
                "INSERT INTO player_status (player_id, status, since) VALUES (%s, %s, NOW())",
                (pid, new_status),
            )

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
    from fastapi.responses import JSONResponse
    from src.api.services.sim_next import sim_next_day

    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    body = await request.json()
    count = body.get("count", 1)  # number of game-days to sim, or "season"

    results = []
    days_simmed = 0
    all_new_injuries = []
    all_returned = []
    remaining = _games_remaining(
        db,
        (
            db.execute(
                """SELECT s.id FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
                (league_id,),
            ).fetchone()["id"]
            if db.execute(
                "SELECT 1 FROM league_seasons WHERE league_id = %s", (league_id,)
            ).fetchone()
            else None
        ),
    )

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
        db,
        (
            db.execute(
                """SELECT s.id FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
                (league_id,),
            ).fetchone()["id"]
            if db.execute(
                "SELECT 1 FROM league_seasons WHERE league_id = %s", (league_id,)
            ).fetchone()
            else None
        ),
    )

    # If season just ended, trigger the state transition (playoffs setup)
    if new_remaining == 0 and days_simmed > 0:
        sim_next_day(league_id, db)

    league_state_row = db.execute(
        "SELECT state FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    # Get updated current date for topbar
    current_season_id = db.execute(
        """SELECT s.id FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
        (league_id,),
    ).fetchone()
    current_date = _current_league_date(
        db,
        current_season_id["id"] if current_season_id else None,
        league_state_row["state"] if league_state_row else "lobby",
    )

    return JSONResponse(
        {
            "days_simmed": days_simmed,
            "games_played": games_played,
            "games_remaining": new_remaining,
            "last_date": results[-1]["game_date"] if results else None,
            "league_state": league_state_row["state"] if league_state_row else None,
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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/")

    # gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, gm, league_id, "standings", user)
    print(f"DEBUG KEYS: {ctx.keys()}")
    season_id = ctx["season_id"]
    my_team_id = gm["team_id"] if gm else None
    teams = []

    if season_id:
        # Base W-L per team
        rows = db.execute(
            """SELECT
                 t.id as team_id, t.city, t.mascot,
                 COALESCE(SUM(tgs.win),  0) as wins,
                 COALESCE(SUM(tgs.loss), 0) as losses,
                 COALESCE(SUM(tgs.runs), 0) as runs_scored
               FROM teams t
               JOIN league_season_teams lst
                 ON lst.team_id = t.id
                 AND lst.league_id = %s
                 AND lst.season_id = %s
               LEFT JOIN (
                 SELECT tgs2.team_id, tgs2.win, tgs2.loss, tgs2.runs
                 FROM team_game_stats tgs2
                 JOIN games g2
                   ON g2.id = tgs2.game_id
                   AND g2.season_id = %s
                   AND g2.completed = 1
                   AND g2.series_id IS NULL
               ) tgs ON tgs.team_id = t.id
               GROUP BY t.id
               ORDER BY wins DESC, losses ASC""",
            (league_id, season_id, season_id),
        ).fetchall()

        ra_rows = db.execute(
            """SELECT tgs.team_id, SUM(opp.runs) as runs_allowed
               FROM team_game_stats tgs
               JOIN games g ON g.id = tgs.game_id AND g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
               JOIN team_game_stats opp
                 ON opp.game_id = g.id AND opp.team_id != tgs.team_id
               GROUP BY tgs.team_id""",
            (season_id,),
        ).fetchall()
        ra_map = {r["team_id"]: r["runs_allowed"] or 0 for r in ra_rows}

        # Home / Away splits
        ha_rows = db.execute(
            """SELECT
                 tgs.team_id,
                 SUM(CASE WHEN g.home_team_id = tgs.team_id AND tgs.win  = 1 THEN 1 ELSE 0 END) as home_wins,
                 SUM(CASE WHEN g.home_team_id = tgs.team_id AND tgs.loss = 1 THEN 1 ELSE 0 END) as home_losses,
                 SUM(CASE WHEN g.away_team_id = tgs.team_id AND tgs.win  = 1 THEN 1 ELSE 0 END) as away_wins,
                 SUM(CASE WHEN g.away_team_id = tgs.team_id AND tgs.loss = 1 THEN 1 ELSE 0 END) as away_losses
               FROM team_game_stats tgs
               JOIN games g ON g.id = tgs.game_id
                 AND g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
               GROUP BY tgs.team_id""",
            (season_id,),
        ).fetchall()
        ha_map = {
            r["team_id"]: {
                "hw": r["home_wins"] or 0,
                "hl": r["home_losses"] or 0,
                "aw": r["away_wins"] or 0,
                "al": r["away_losses"] or 0,
            }
            for r in ha_rows
        }

        human_team_ids = {
            r["team_id"]
            for r in db.execute(
                "SELECT team_id FROM gms WHERE league_id = %s AND is_ai = 0 AND team_id IS NOT NULL",
                (league_id,),
            ).fetchall()
        }

        # Recent game results per team for streak (last 10 games ordered newest first)
        recent_rows = db.execute(
            """SELECT tgs.team_id, tgs.win, g.game_date
               FROM team_game_stats tgs
               JOIN games g ON g.id = tgs.game_id
               WHERE g.season_id = %s AND g.completed = 1
               ORDER BY g.game_date DESC""",
            (season_id,),
        ).fetchall()

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
        from src.league.statistics.print_standings import (
            sort_standings as _sort_standings,
        )

        raw_rows = []
        for r in rows:
            wins = r["wins"] or 0
            losses = r["losses"] or 0
            played = wins + losses
            raw_rows.append(
                {
                    **dict(r),
                    "win_pct": wins / played if played else 0.0,
                    "runs_scored": r["runs_scored"] or 0,
                }
            )
        ranked = _sort_standings(db, season_id, raw_rows)
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
            up_rows = db.execute(
                """SELECT g.id, g.game_date, g.home_team_id, g.away_team_id,
                          ht.city as home_city, ht.mascot as home_mascot,
                          at.city as away_city, at.mascot as away_mascot
                   FROM games g
                   JOIN teams ht ON ht.id = g.home_team_id
                   JOIN teams at ON at.id = g.away_team_id
                   WHERE g.season_id = %s AND g.completed = 0
                     AND (g.home_team_id = %s OR g.away_team_id = %s)
                   ORDER BY g.game_date LIMIT 3""",
                (season_id, my_team_id, my_team_id),
            ).fetchall()
            for g_row in up_rows:
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

        # ── My last 3 completed games ─────────────────────────────────────────
        recent_games = []
        if my_team_id:
            rg_rows = db.execute(
                """SELECT g.id as game_id, g.game_date, g.home_team_id, g.away_team_id,
                          g.home_score, g.away_score,
                          ht.city as home_city, ht.mascot as home_mascot,
                          at.city as away_city, at.mascot as away_mascot
                   FROM games g
                   JOIN teams ht ON ht.id = g.home_team_id
                   JOIN teams at ON at.id = g.away_team_id
                   WHERE g.season_id = %s AND g.completed = 1
                     AND (g.home_team_id = %s OR g.away_team_id = %s)
                   ORDER BY g.game_date DESC LIMIT 5""",
                (season_id, my_team_id, my_team_id),
            ).fetchall()
            for g_row in rg_rows:
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
            inj_rows = db.execute(
                """SELECT p.id as player_id, p.first_name, p.last_name, pi.games_remaining
                   FROM player_injuries pi
                   JOIN players p ON p.id = pi.player_id
                   JOIN team_players tp ON tp.player_id = p.id AND tp.team_id = %s
                   WHERE pi.games_remaining > 0
                     AND (pi.league_id = %s OR pi.league_id = '')
                   ORDER BY pi.games_remaining DESC""",
                (my_team_id, league_id),
            ).fetchall()
            injuries = []
            for r in inj_rows:
                d = dict(r)
                raw = d.get("games_remaining", 0) or 0
                d["games_remaining"] = raw
                injuries.append(d)

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
):
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/")

    # gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, gm, league_id, "leaders", user)
    season_id = ctx["season_id"]
    my_team_id = gm["team_id"] if gm else None

    def top(rows, key, n=10, asc=False):
        return sorted(rows, key=lambda r: r[key] or 0, reverse=not asc)[:n]

    def fmt_avg(v):
        return f"{v:.3f}" if v else ".000"

    def fmt_era(v):
        return f"{v:.2f}" if v else "0.00"

    def ip_str(outs):
        o = outs or 0
        return f"{o//3}.{o%3}"

    bat_cats = []
    pit_cats = []

    if season_id:
        # Team games played — basis for qualification thresholds
        tg_row = db.execute(
            """SELECT MAX(bat_games_played) as tg FROM player_season_stats
               WHERE season_id = %s AND is_postseason = 0""",
            (season_id,),
        ).fetchone()
        team_games = tg_row["tg"] or 1

        min_ab = int(3.1 * team_games)  # qualify for rate stats
        min_outs = int(3 * team_games)  # 1 IP per team game

        # ── Batting: one query, compute rate stats, build all categories ────────
        bat_rows = db.execute(
            """SELECT pss.player_id, p.first_name, p.last_name, t.city, t.mascot, pss.team_id,
                      pss.bat_ab, pss.bat_hits, pss.bat_doubles, pss.bat_triples,
                      pss.bat_home_runs, pss.bat_rbi, pss.bat_runs, pss.bat_walks,
                      pss.bat_strike_outs, pss.bat_stolen_bases, pss.bat_hbp, pss.bat_sac_flys,
                      pss.bat_games_played
               FROM player_season_stats pss
               JOIN players p ON p.id = pss.player_id
               JOIN teams t ON t.id = pss.team_id
               JOIN league_season_teams lst
                 ON lst.team_id = pss.team_id AND lst.season_id = pss.season_id AND lst.league_id = %s
               WHERE pss.season_id = %s AND pss.is_postseason = 0 AND pss.bat_ab >= 1""",
            (league_id, season_id),
        ).fetchall()

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

        # ── Pitching: one query, compute rate stats, build all categories ──────
        pit_rows = db.execute(
            """SELECT pss.player_id, p.first_name, p.last_name, t.city, t.mascot, pss.team_id,
                      pss.pitch_games_played, pss.pitch_games_started, pss.pitch_wins,
                      pss.pitch_losses, pss.pitch_saves, pss.pitch_outs,
                      pss.pitch_hits, pss.pitch_earned_runs, pss.pitch_walks,
                      pss.pitch_strike_outs, pss.pitch_home_runs
               FROM player_season_stats pss
               JOIN players p ON p.id = pss.player_id
               JOIN teams t ON t.id = pss.team_id
               JOIN league_season_teams lst
                 ON lst.team_id = pss.team_id AND lst.season_id = pss.season_id AND lst.league_id = %s
               WHERE pss.season_id = %s AND pss.is_postseason = 0 AND pss.pitch_outs >= 9""",
            (league_id, season_id),
        ).fetchall()

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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/")

    # gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, gm, league_id, "roster", user)
    players = []
    team_id = gm["team_id"]

    if team_id:
        rows = db.execute(
            """SELECT p.*, ps_stat.status, sk.*
               FROM players p
               JOIN team_players tp ON tp.player_id = p.id AND tp.team_id = %s
               JOIN player_status ps_stat ON ps_stat.player_id = p.id
               LEFT JOIN player_skills sk ON sk.player_id = p.id
               ORDER BY ps_stat.status, p.last_name""",
            (team_id,),
        ).fetchall()
        for row in rows:
            d = dict(row)
            # skills_row = db.execute(
            #     "SELECT * FROM player_skills WHERE player_id = %s", (d["id"],)
            # ).fetchone()
            # skills = dict(skills_row) if skills_row else {}
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
        stat_rows = db.execute(
            """SELECT player_id,
                      bat_games_played, bat_hits, bat_ab, bat_home_runs, bat_rbi,
                      pitch_games_started, pitch_outs, pitch_earned_runs,
                      pitch_wins, pitch_losses, pitch_saves
               FROM player_season_stats
               WHERE season_id = %s AND is_postseason = 0
                 AND player_id IN (
                     SELECT player_id FROM team_players WHERE team_id = %s
                 )""",
            (season_id, gm["team_id"]),
        ).fetchall()
        stats_map = {r["player_id"]: r for r in stat_rows}
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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/")

    # gm = _resolve_gm(db, user["id"], league_id)
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

    # Load all 40-man players with grades
    rows = db.execute(
        """SELECT p.*, ps.status FROM players p
           JOIN team_players tp ON tp.player_id = p.id AND tp.team_id = %s
           JOIN player_status ps ON ps.player_id = p.id
           WHERE ps.status IN ('26man', '40man')
           ORDER BY p.last_name""",
        (team_id,),
    ).fetchall()

    hitters = []
    pitchers = []
    for row in rows:
        d = dict(row)
        sk = db.execute(
            "SELECT * FROM player_skills WHERE player_id = %s", (d["id"],)
        ).fetchone()
        skills = dict(sk) if sk else {}
        grades = player_row_to_grades(d, skills, d["status"])
        ratings = _compute_ratings(skills, d.get("throws", "R"))
        g = grades.model_dump()
        if ratings:
            if g.get("player_type") == "pitcher":
                best_p = max(ratings.get("sp", 0), ratings.get("rp", 0))
                g["overall"] = skill_to_grade(best_p) if best_p else g["overall"]
                g["sp_grade"] = skill_to_grade(ratings.get("sp", 0))
                g["rp_grade"] = skill_to_grade(ratings.get("rp", 0))
            else:
                g["overall"] = skill_to_grade(ratings.get("overall_player"))
                g["leadoff_grade"] = skill_to_grade(ratings.get("lead_off", 0))
                g["power_h_grade"] = skill_to_grade(ratings.get("power_hitter", 0))
                g["contact_h_grade"] = skill_to_grade(ratings.get("contact_hitter", 0))
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
        # Raw skill grades not in PlayerGrades — needed for sort
        g["base_running"] = skill_to_grade(skills.get("base_running"))
        g["bunting"] = skill_to_grade(skills.get("bunting"))
        g["ground_balls"] = skill_to_grade(skills.get("ground_balls"))
        if g.get("player_type") == "pitcher":
            pitchers.append(g)
        else:
            hitters.append(g)

    # Load saved lineup preferences
    saved_lineup = []
    prefs = db.execute(
        """SELECT player_id, batting_order, position FROM gm_lineup_preferences
           WHERE gm_id = %s AND batting_order IS NOT NULL
           ORDER BY batting_order""",
        (gm["id"],),
    ).fetchall()
    saved_lineup = [
        {
            "player_id": r["player_id"],
            "batting_order": r["batting_order"],
            "position": r["position"],
        }
        for r in prefs
    ]

    # Load saved rotation
    saved_rotation = []
    if season_id:
        rot = db.execute(
            """SELECT player_id, rotation_order FROM team_rotations
               WHERE team_id = %s AND season_id = %s AND end_date IS NULL
               ORDER BY rotation_order""",
            (team_id, season_id),
        ).fetchall()
        saved_rotation = [r["player_id"] for r in rot]

    # Load saved bullpen roles
    saved_bullpen = {}
    if season_id:
        bp = db.execute(
            """SELECT player_id, role FROM bullpen_roles
               WHERE team_id = %s AND season_id = %s AND end_date IS NULL""",
            (team_id, season_id),
        ).fetchall()
        saved_bullpen = {r["player_id"]: r["role"] for r in bp}

    # Load rotation pointer (green light position)
    saved_rotation_pointer = None
    if season_id and saved_rotation:
        ptr_row = db.execute(
            """SELECT next_order FROM team_rotation_pointer
               WHERE team_id = %s AND season_id = %s AND series_id = ''""",
            (team_id, season_id),
        ).fetchone()
        if ptr_row:
            rot_at_ptr = db.execute(
                """SELECT player_id FROM team_rotations
                   WHERE team_id = %s AND season_id = %s AND rotation_order = %s
                   AND end_date IS NULL""",
                (team_id, season_id, ptr_row["next_order"]),
            ).fetchone()
            if rot_at_ptr:
                saved_rotation_pointer = rot_at_ptr["player_id"]

    # Attach season stats to each player for display
    if season_id:
        stat_rows = db.execute(
            """SELECT player_id,
                      bat_ab, bat_hits, bat_home_runs,
                      pitch_games_started, pitch_outs, pitch_earned_runs,
                      pitch_wins, pitch_losses, pitch_saves
               FROM player_season_stats
               WHERE season_id = %s AND is_postseason = 0""",
            (season_id,),
        ).fetchall()
        stats_map = {r["player_id"]: r for r in stat_rows}
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
            if s and (s["pitch_outs"] or 0) > 0:
                outs = s["pitch_outs"]
                era = (s["pitch_earned_runs"] * 27) / outs
                p["stat_gs"] = s["pitch_games_started"] or 0
                p["stat_era"] = f"{era:.2f}"
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
    league_row = db.execute(
        "SELECT state FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    ctx["is_playoffs"] = league_row and league_row["state"] == "playoffs"
    return tab_response(request, htmx, "dashboard/partials/lineup.html", ctx)


@router.put("/leagues/{league_id}/lineup/save")
async def save_lineup_prefs(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
    # gm_session: str | None = Cookie(default=None),
):
    from fastapi.responses import JSONResponse

    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    # gm = _resolve_gm(db, user["id"], league_id)
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
    # db.execute("DELETE FROM gm_lineup_preferences WHERE gm_id = %s", (gm["id"],))
    # for slot in lineup:
    #     db.execute(
    #         """INSERT INTO gm_lineup_preferences
    #            (gm_id, player_id, batting_order, position, is_starter, updated_at)
    #            VALUES (%s, %s, %s, %s, 1, NOW())""",
    #         (gm["id"], slot["player_id"], slot["batting_order"], slot.get("position")),
    #     )

    db.commit()
    return JSONResponse({"saved": True})


@router.put("/leagues/{league_id}/rotation/save")
async def save_rotation(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
):
    from fastapi.responses import JSONResponse

    if not gm["team_id"]:
        return JSONResponse({"detail": "No team"}, status_code=400)

    body = await request.json()
    rotation = body.get("rotation", [])
    pointer_pid = body.get("pointer_pid", None)

    season_row = db.execute(
        """SELECT s.id FROM seasons s
           JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
        (league_id,),
    ).fetchone()
    if not season_row:
        return JSONResponse({"detail": "No active season"}, status_code=400)
    season_id = season_row["id"]
    team_id = gm["team_id"]

    season_start_row = db.execute(
        "SELECT MIN(game_date) as start FROM games WHERE season_id = %s",
        (season_id,),
    ).fetchone()
    effective_date = (
        season_start_row["start"]
        if season_start_row and season_start_row["start"]
        else "2000-01-01"
    )

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
    from fastapi.responses import JSONResponse
    from fastapi import HTTPException

    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    # 1. Resolve Season (You could eventually move this to a dependency too!)
    season = db.execute(
        """SELECT s.id FROM seasons s 
           JOIN league_seasons ls ON ls.season_id = s.id 
           WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
        (league_id,),
    ).fetchone()

    if not season:
        raise HTTPException(status_code=400, detail="No active season")

    # gm = _resolve_gm(db, user["id"], league_id)
    # if not gm or not gm["team_id"]:
    #     return JSONResponse({"detail": "No team"}, status_code=400)

    # body = await request.json()
    # bullpen = body.get("bullpen", {})

    # season_id = db.execute(
    #     """SELECT s.id FROM seasons s
    #        JOIN league_seasons ls ON ls.season_id = s.id
    #        WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
    #     (league_id,),
    # ).fetchone()

    season_id = season["id"]

    # season_id = season_id["id"] if season_id else None
    # if not season_id:
    #     return JSONResponse({"detail": "No active season"}, status_code=400)

    season_start_row = db.execute(
        "SELECT MIN(game_date) as start FROM games WHERE season_id = %s",
        (season_id,),
    ).fetchone()
    effective_date = (
        season_start_row["start"]
        if season_start_row and season_start_row["start"]
        else "2000-01-01"
    )

    # Format assignments for the Repo
    # We transform {"player_id": "role"} -> [{"player_id": "...", "role": "..."}]
    # raw_bullpen = body.get("bullpen", {})
    assignments = [
        {"player_id": pid, "role": role} for pid, role in body.bullpen.items()
    ]
    from src.db.repositories.bullpen_roles_repo import BullpenRepository

    bp_repo = BullpenRepository(db)

    try:
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

    # # Replace bullpen roles
    # db.execute(
    #     "DELETE FROM bullpen_roles WHERE team_id = %s AND season_id = %s AND end_date IS NULL",
    #     (gm["team_id"], season_id),
    # )
    # valid_roles = {"Closer", "Setup", "Middle", "Long", "Specialist", "Utility"}
    # for pid, role in bullpen.items():
    #     if role in valid_roles:
    #         db.execute(
    #             """INSERT INTO bullpen_roles
    #                (team_id, player_id, season_id, role, effective_date)
    #                VALUES (%s, %s, %s, %s, %s)""",
    #             (gm["team_id"], pid, season_id, role, effective_date),
    #         )

    # db.commit()
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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/")

    # gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, gm, league_id, "strategy", user)

    profile_row = (
        db.execute("SELECT * FROM gm_profiles WHERE gm_id = %s", (gm["id"],)).fetchone()
        if gm
        else None
    )

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
        p = dict(profile_row)
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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return HTMLResponse("Unauthorized", status_code=401)

    # gm = _resolve_gm(db, user["id"], league_id)
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

    set_clause = ", ".join(f"{col} = %s" for col in updates)
    db.execute(
        f"UPDATE gm_profiles SET {set_clause}, updated_at = NOW() WHERE gm_id = %s",
        [*updates.values(), gm["id"]],
    )
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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/")

    # gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, gm, league_id, "schedule", user)
    season_id = ctx["season_id"]
    my_team_id = gm["team_id"] if gm else None

    upcoming = []
    recent = []

    if season_id and my_team_id:
        # Upcoming games — all remaining for my team
        up_rows = db.execute(
            """SELECT g.game_date, g.home_team_id, g.away_team_id,
                      ht.city as home_city, ht.mascot as home_mascot,
                      at.city as away_city, at.mascot as away_mascot
               FROM games g
               JOIN teams ht ON ht.id = g.home_team_id
               JOIN teams at ON at.id = g.away_team_id
               WHERE g.season_id = %s AND g.completed = 0
                 AND (g.home_team_id = %s OR g.away_team_id = %s)
               ORDER BY g.game_date""",
            (season_id, my_team_id, my_team_id),
        ).fetchall()
        # Build opponent W-L record map for upcoming games
        opp_team_ids = set()
        for r in up_rows:
            opp_id = (
                r["away_team_id"]
                if r["home_team_id"] == my_team_id
                else r["home_team_id"]
            )
            opp_team_ids.add(opp_id)

        opp_records: dict[str, str] = {}
        if opp_team_ids:
            placeholders = ", ".join(["%s"] * len(opp_team_ids))
            wl_rows = db.execute(
                f"""SELECT tgs.team_id,
                           COALESCE(SUM(tgs.win),  0) as wins,
                           COALESCE(SUM(tgs.loss), 0) as losses
                    FROM team_game_stats tgs
                    JOIN games g ON g.id = tgs.game_id
                      AND g.season_id = %s AND g.completed = 1 AND g.series_id IS NULL
                    WHERE tgs.team_id IN ({placeholders})
                    GROUP BY tgs.team_id""",
                (season_id, *opp_team_ids),
            ).fetchall()
            for wl in wl_rows:
                opp_records[wl["team_id"]] = f"{wl['wins']}-{wl['losses']}"

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

        # Recent results — all completed
        rec_rows = db.execute(
            """SELECT g.id as game_id, g.game_date, g.home_team_id, g.away_team_id,
                      g.home_score, g.away_score, g.innings_played,
                      ht.city as home_city, ht.mascot as home_mascot,
                      at.city as away_city, at.mascot as away_mascot
               FROM games g
               JOIN teams ht ON ht.id = g.home_team_id
               JOIN teams at ON at.id = g.away_team_id
               WHERE g.season_id = %s AND g.completed = 1
                 AND (g.home_team_id = %s OR g.away_team_id = %s)
               ORDER BY g.game_date DESC""",
            (season_id, my_team_id, my_team_id),
        ).fetchall()
        for r in rec_rows:
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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/")

    # gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, gm, league_id, "stats", user)
    current_season_id = ctx["season_id"]
    my_team_id = gm["team_id"] if gm else None

    # All seasons for this league, newest first
    all_seasons = db.execute(
        """SELECT s.id, s.year FROM seasons s
           JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s
           ORDER BY s.year DESC""",
        (league_id,),
    ).fetchall()

    # Default to current season
    selected_season_id = season_id or current_season_id
    is_postseason = bool(postseason)

    # Default to user's team
    selected_team_id = team_id or my_team_id

    # All teams for the selected season
    all_teams = (
        db.execute(
            """SELECT DISTINCT t.id, t.city, t.mascot
           FROM teams t
           JOIN league_season_teams lst ON lst.team_id = t.id
           WHERE lst.league_id = %s AND lst.season_id = %s
           ORDER BY t.city""",
            (league_id, selected_season_id),
        ).fetchall()
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
    ps_flag = 1 if is_postseason else 0

    if selected_season_id and selected_team_id:
        tg_row = db.execute(
            """SELECT MAX(bat_games_played) as tg FROM player_season_stats
               WHERE season_id = %s AND is_postseason = %s
                 AND team_id = %s""",
            (selected_season_id, ps_flag, selected_team_id),
        ).fetchone()
        team_games = tg_row["tg"] or 0
        min_ab = int(3.1 * team_games) if not is_postseason else 0
        min_outs = int(3 * team_games) if not is_postseason else 0

        rows = db.execute(
            """SELECT p.id as player_id, p.first_name, p.last_name, pss.*
               FROM player_season_stats pss
               JOIN players p ON p.id = pss.player_id
               WHERE pss.season_id = %s AND pss.is_postseason = %s
                 AND pss.team_id = %s""",
            (selected_season_id, ps_flag, selected_team_id),
        ).fetchall()

        for r in rows:
            s = dict(r)
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
            "all_teams": [dict(t) for t in all_teams],
            "all_seasons": [dict(s) for s in all_seasons],
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
    from src.league.playoffs.play_playoffs import (
        get_series_id,
    )

    ROUND_DEFS = [
        {"name": "Round 1", "series_names": ["1v8", "4v5", "2v7", "3v6"], "best_of": 5},
        {
            "name": "Semifinals",
            "series_names": ["[1,8]v[4,5]", "[2,7]v[3,6]"],
            "best_of": 7,
        },
        {"name": "Finals", "series_names": ["Finals"], "best_of": 7},
    ]

    from src.league.playoffs.play_playoffs import get_series_winner as _gsw

    # Map semifinal series name → which round-1 series feed into it
    _SEMI_FEEDERS = {
        "[1,8]v[4,5]": ("1v8", "4v5"),
        "[2,7]v[3,6]": ("2v7", "3v6"),
    }

    def _team_name(tid):
        r = db.execute(
            "SELECT city, mascot FROM teams WHERE id = %s", (tid,)
        ).fetchone()
        return f"{r['city']} {r['mascot']}" if r else tid

    def load_series(series_name, best_of):
        sid = get_series_id(db, season_id, series_name)
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

        games = db.execute(
            """SELECT id, game_date, home_team_id, away_team_id,
                      completed, home_score, away_score, winner_id
               FROM games WHERE series_id = %s ORDER BY game_date""",
            (sid,),
        ).fetchall()

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
                feeder_sid = get_series_id(db, season_id, feeder_name)
                if feeder_sid:
                    w = _gsw(db, feeder_sid, 5)
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

        return {
            "name": series_name,
            "series_id": sid,
            "best_of": best_of,
            "wins_needed": wins_needed,
            "teams": teams,
            "games_played": games_played,
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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/")
    # gm = _resolve_gm(db, user["id"], league_id)
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
    from fastapi.responses import JSONResponse

    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from src.api.services.sim_playoff import sim_playoff

    result = sim_playoff(league_id, db, mode=mode)

    league_state = db.execute(
        "SELECT state FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()["state"]
    result["league_state"] = league_state
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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return HTMLResponse("Unauthorized", status_code=401)

    # gm = _resolve_gm(db, user["id"], league_id)
    # my_team_id = gm["team_id"] if gm else None
    my_team_id = gm["team_id"]
    # print(f"DEBUG: My team ID: {my_team_id}")

    game = db.execute(
        """SELECT g.*, ht.city as home_city, ht.mascot as home_mascot,
                  at.city as away_city, at.mascot as away_mascot
           FROM games g
           JOIN teams ht ON ht.id = g.home_team_id
           JOIN teams at ON at.id = g.away_team_id
           WHERE g.id = %s""",
        (game_id,),
    ).fetchone()
    if not game:
        return HTMLResponse("Game not found", status_code=404)
    game = dict(game)

    # Box score — batting
    bat_rows = db.execute(
        """SELECT p.first_name, p.last_name, pgs.team_id,
                  pgs.bat_ab as "AB", pgs.bat_runs as "R", pgs.bat_hits as "H",
                  pgs.bat_doubles as doubles, pgs.bat_triples as triples,
                  pgs.bat_home_runs as "HR", pgs.bat_rbi as "RBI",
                  pgs.bat_walks as "BB", pgs.bat_strike_outs as "K",
                  pgs.bat_stolen_bases as "SB", pgs.bat_hbp as "HBP",
                  pgs.bat_sac_flys as "SF",
                  pgs.bat_game_started as started
           FROM player_game_stats pgs
           JOIN players p ON p.id = pgs.player_id
           WHERE pgs.game_id = %s AND pgs.bat_ab > 0
           ORDER BY pgs.team_id, pgs.bat_game_started DESC, p.last_name""",
        (game_id,),
    ).fetchall()

    # Box score — pitching
    pit_rows = db.execute(
        """SELECT p.first_name, p.last_name, pgs.team_id,
                  pgs.pitch_outs as outs, pgs.pitch_hits as "H",
                  pgs.pitch_runs as "R", pgs.pitch_earned_runs as "ER",
                  pgs.pitch_walks as "BB", pgs.pitch_strike_outs as "K",
                  pgs.pitch_home_runs as "HR", pgs.pitch_win as "W",
                  pgs.pitch_loss as "L", pgs.pitch_save as "SV",
                  pgs.pitch_game_started as started
           FROM player_game_stats pgs
           JOIN players p ON p.id = pgs.player_id
           WHERE pgs.game_id = %s AND pgs.pitch_outs > 0
           ORDER BY pgs.team_id, pgs.pitch_game_started DESC, pgs.pitch_outs DESC""",
        (game_id,),
    ).fetchall()

    # Format pitching IP
    def fmt_ip(outs):
        return f"{outs//3}.{outs%3}"

    home_bat = [dict(r) for r in bat_rows if r["team_id"] == game["home_team_id"]]
    away_bat = [dict(r) for r in bat_rows if r["team_id"] == game["away_team_id"]]
    home_pit = [dict(r) for r in pit_rows if r["team_id"] == game["home_team_id"]]
    away_pit = [dict(r) for r in pit_rows if r["team_id"] == game["away_team_id"]]
    for p in home_pit + away_pit:
        p["IP"] = fmt_ip(p["outs"] or 0)

    # Event log
    events = db.execute(
        """SELECT ge.event_type, ge.inning, ge.half, ge.reason,
                  ge.detail, ge.team_id
           FROM game_events ge
           WHERE ge.game_id = %s
           ORDER BY ge.id""",
        (game_id,),
    ).fetchall()
    import json as _json

    events_out = []
    for e in events:
        ed = dict(e)
        if ed.get("detail"):
            try:
                ed["detail_parsed"] = _json.loads(ed["detail"])
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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/")
    # gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, gm, league_id, user)
    my_team_id = gm["team_id"] if gm else None

    # Use explicit season_id (from history link) or fall back to last season with series
    if not season_id:
        row = db.execute(
            """SELECT s.id FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s
                 AND EXISTS (SELECT 1 FROM series sr WHERE sr.season_id = s.id)
               ORDER BY s.year DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
        season_id = row["id"] if row else ctx["season_id"]

    # My team record
    my_record = None
    if my_team_id and season_id:
        r = db.execute(
            """SELECT SUM(tgs.win) as w, SUM(tgs.loss) as l
               FROM team_game_stats tgs
               JOIN games g ON g.id = tgs.game_id
               WHERE tgs.team_id = %s AND g.season_id = %s AND g.series_id IS NULL""",
            (my_team_id, season_id),
        ).fetchone()
        if r:
            my_record = {"w": r["w"] or 0, "l": r["l"] or 0}

    # Champion
    champion = None
    if season_id:
        finals = db.execute(
            "SELECT id FROM series WHERE season_id = %s AND name = 'Finals'",
            (season_id,),
        ).fetchone()
        if finals:
            champ_row = db.execute(
                """SELECT winner_id, COUNT(*) as wins FROM games
                   WHERE series_id = %s AND completed = 1
                   GROUP BY winner_id ORDER BY wins DESC LIMIT 1""",
                (finals["id"],),
            ).fetchone()
            if champ_row and champ_row["wins"] >= 4:
                t = db.execute(
                    "SELECT city, mascot FROM teams WHERE id = %s",
                    (champ_row["winner_id"],),
                ).fetchone()
                if t:
                    champion = {
                        "team_id": champ_row["winner_id"],
                        "name": f"{t['city']} {t['mascot']}",
                        "is_mine": champ_row["winner_id"] == my_team_id,
                    }

    # My playoff result
    my_playoff_result = None
    if my_team_id and season_id:
        for series_name, best_of in [
            ("Finals", 7),
            ("[1,8]v[4,5]", 7),
            ("[2,7]v[3,6]", 7),
            ("1v8", 5),
            ("2v7", 5),
            ("3v6", 5),
            ("4v5", 5),
        ]:
            sid = db.execute(
                "SELECT id FROM series WHERE season_id = %s AND name = %s",
                (season_id, series_name),
            ).fetchone()
            if not sid:
                continue
            appeared = db.execute(
                """SELECT 1 FROM games WHERE series_id = %s
                   AND (home_team_id = %s OR away_team_id = %s) LIMIT 1""",
                (sid["id"], my_team_id, my_team_id),
            ).fetchone()
            if appeared:
                wins_needed = {5: 3, 7: 4}[best_of]
                wins_row = db.execute(
                    """SELECT winner_id, COUNT(*) as wins FROM games
                       WHERE series_id = %s AND completed = 1 AND winner_id = %s
                       GROUP BY winner_id""",
                    (sid["id"], my_team_id),
                ).fetchone()
                my_wins = wins_row["wins"] if wins_row else 0
                if my_wins >= wins_needed:
                    my_playoff_result = f"Won {series_name}"
                else:
                    my_playoff_result = f"Eliminated in {series_name}"
                break

    # Stat leaders — compute qualification thresholds from actual games played
    bat_leader = pit_leader = None
    if season_id:
        games_row = db.execute(
            """SELECT COUNT(*) as g FROM games
               WHERE season_id = %s AND completed = 1 AND series_id IS NULL""",
            (season_id,),
        ).fetchone()
        num_teams_row = db.execute(
            "SELECT COUNT(DISTINCT team_id) as n FROM league_season_teams WHERE season_id = %s",
            (season_id,),
        ).fetchone()
        num_teams = num_teams_row["n"] or 30
        games_total = games_row["g"] or 0
        games_per_team = (games_total * 2) / num_teams if num_teams else 0
        min_ab = int(3.1 * games_per_team)
        min_outs = int(3 * games_per_team)

        br = db.execute(
            """SELECT p.first_name, p.last_name, t.city, t.mascot,
                      CAST(pss.bat_hits AS REAL)/NULLIF(pss.bat_ab,0) as avg
               FROM player_season_stats pss
               JOIN players p ON p.id = pss.player_id
               JOIN teams t ON t.id = pss.team_id
               JOIN league_season_teams lst ON lst.team_id=pss.team_id AND lst.season_id=pss.season_id AND lst.league_id=%s
               WHERE pss.season_id=%s AND pss.is_postseason=0 AND pss.bat_ab >= %s
               ORDER BY avg DESC LIMIT 1""",
            (league_id, season_id, min_ab),
        ).fetchone()
        if br:
            bat_leader = {
                "name": f"{br['first_name']} {br['last_name']}",
                "team": f"{br['city']} {br['mascot']}",
                "stat": f"{br['avg']:.3f}",
                "label": "AVG",
            }

        pr = db.execute(
            """SELECT p.first_name, p.last_name, t.city, t.mascot,
                      CAST(pss.pitch_earned_runs*27 AS REAL)/NULLIF(pss.pitch_outs,0) as era
               FROM player_season_stats pss
               JOIN players p ON p.id = pss.player_id
               JOIN teams t ON t.id = pss.team_id
               JOIN league_season_teams lst ON lst.team_id=pss.team_id AND lst.season_id=pss.season_id AND lst.league_id=%s
               WHERE pss.season_id=%s AND pss.is_postseason=0 AND pss.pitch_outs >= %s
               ORDER BY era ASC LIMIT 1""",
            (league_id, season_id, min_outs),
        ).fetchone()
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
        sy = db.execute(
            "SELECT year FROM seasons WHERE id = %s", (season_id,)
        ).fetchone()
        season_year = sy["year"] if sy else None

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


@router.post("/leagues/{league_id}/offseason/begin")
def begin_offseason(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
):
    from fastapi.responses import JSONResponse

    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from src.api.services.offseason_service import run_offseason

    try:
        result = run_offseason(league_id, db)
        return JSONResponse({"ok": True, **result})
    except Exception as e:
        import traceback

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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/")
    # gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, gm, league_id, user)
    my_team_id = gm["team_id"] if gm else None

    seasons = db.execute(
        """SELECT s.id, s.year, s.name
           FROM seasons s
           JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s
           ORDER BY s.year DESC""",
        (league_id,),
    ).fetchall()

    history_rows = []
    for s in seasons:
        # Champion
        finals = db.execute(
            "SELECT id FROM series WHERE season_id = %s AND name = 'Finals'",
            (s["id"],),
        ).fetchone()
        champion_name = None
        if finals:
            champ = db.execute(
                """SELECT winner_id, COUNT(*) as wins FROM games
                   WHERE series_id = %s AND completed=1
                   GROUP BY winner_id ORDER BY wins DESC LIMIT 1""",
                (finals["id"],),
            ).fetchone()
            if champ and champ["wins"] >= 4:
                t = db.execute(
                    "SELECT city, mascot FROM teams WHERE id = %s",
                    (champ["winner_id"],),
                ).fetchone()
                if t:
                    champion_name = f"{t['city']} {t['mascot']}"

        # My team record
        my_w = my_l = None
        if my_team_id:
            r = db.execute(
                """SELECT SUM(tgs.win) as w, SUM(tgs.loss) as l
                   FROM team_game_stats tgs
                   JOIN games g ON g.id=tgs.game_id
                   WHERE tgs.team_id=%s AND g.season_id=%s AND g.series_id IS NULL""",
                (my_team_id, s["id"]),
            ).fetchone()
            if r and (r["w"] or r["l"]):
                my_w, my_l = r["w"] or 0, r["l"] or 0

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
    return tab_response(request, "dashboard/partials/history.html", ctx)


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
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return HTMLResponse("Unauthorized", status_code=401)

    # gm = _resolve_gm(db, user["id"], league_id)

    def _load(pid: str) -> dict | None:
        p = db.execute("SELECT * FROM players WHERE id = %s", (pid,)).fetchone()
        if not p:
            return None
        sk = db.execute(
            "SELECT * FROM player_skills WHERE player_id = %s", (pid,)
        ).fetchone()
        st = db.execute(
            "SELECT status FROM player_status WHERE player_id = %s", (pid,)
        ).fetchone()
        en = db.execute(
            "SELECT * FROM player_energy WHERE player_id = %s AND league_id = %s",
            (pid, league_id),
        ).fetchone()
        inj = db.execute(
            "SELECT * FROM player_injury_log WHERE player_id = %s ORDER BY injury_date DESC LIMIT 5",
            (pid,),
        ).fetchall()
        team = db.execute(
            """SELECT t.city, t.mascot FROM teams t
               JOIN team_players tp ON tp.team_id = t.id WHERE tp.player_id = %s""",
            (pid,),
        ).fetchone()

        skills = dict(sk) if sk else {}
        grades = player_row_to_grades(
            dict(p), skills, st["status"] if st else "unassigned"
        )
        ratings = _compute_ratings(skills, dict(p).get("throws", "R"))

        # Season stats — find current season for this league
        season_row = db.execute(
            """SELECT ls.season_id FROM league_seasons ls JOIN seasons s ON s.id = ls.season_id WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
        stats = None
        if season_row:
            stats_row = db.execute(
                """SELECT * FROM player_season_stats
                   WHERE player_id = %s AND season_id = %s AND is_postseason = 0""",
                (pid, season_row["season_id"]),
            ).fetchone()
            if stats_row:
                s = dict(stats_row)
                is_pitcher = grades.player_type == "pitcher"
                if is_pitcher and s.get("pitch_games_played", 0) > 0:
                    outs = s.get("pitch_outs", 0) or 0
                    ip = outs // 3 + (outs % 3) / 10
                    er = s.get("pitch_earned_runs", 0) or 0
                    era = round((er * 27) / outs, 2) if outs > 0 else 0.0
                    walks = s.get("pitch_walks", 0) or 0
                    hits = s.get("pitch_hits", 0) or 0
                    whip = round((walks + hits) / (outs / 3), 2) if outs > 0 else 0.0
                    stats = {
                        "G": s.get("pitch_games_played", 0),
                        "GS": s.get("pitch_games_started", 0),
                        "W": s.get("pitch_wins", 0),
                        "L": s.get("pitch_losses", 0),
                        "SV": s.get("pitch_saves", 0),
                        "IP": round(ip, 1),
                        "H": hits,
                        "ER": er,
                        "BB": walks,
                        "K": s.get("pitch_strike_outs", 0),
                        "ERA": era,
                        "WHIP": whip,
                    }
                elif not is_pitcher and s.get("bat_games_played", 0) > 0:
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
                    stats = {
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
        status = st["status"] if st else "unassigned"
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

        grade_map = _ratings_to_grade_map(grades, skills, ratings)

        # Best defensive grade for card display
        best_def_grade = skill_to_grade(ratings.get("best_def")) if ratings else "%s"
        best_def_label = ratings.get("best_def_label", "DEF") if ratings else "DEF"

        energy = None
        if en:
            energy = {
                "current": round(en["current_energy"] * 100),
                "max": round(en["max_energy"] * 100),
                "consecutive_days": en["consecutive_days"],
                "last_game_date": en["last_game_date"],
                "season_games_played": en["season_games_played"],
            }

        # Injury status
        inj_status = db.execute(
            """SELECT games_remaining FROM player_injuries
               WHERE player_id = %s AND games_remaining > 0
               AND (league_id = %s OR league_id = '')
               LIMIT 1""",
            (pid, league_id),
        ).fetchone()
        raw_injury = inj_status["games_remaining"] if inj_status else None

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
            "injury_log": [dict(r) for r in inj],
            "stats": stats,
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


@router.get("/leagues/{league_id}/history/{year}/", response_class=HTMLResponse)
def history_season_detail(
    request: Request,
    league_id: str,
    year: int,
    db: DB,
    gm: GM,
):
    # user = _resolve_user(db, gm_session)
    # if not user:
    #     return RedirectResponse("/")

    # gm = _resolve_gm(db, user["id"], league_id)

    season = db.execute(
        """SELECT s.* FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = %s AND s.year = %s""",
        (league_id, year),
    ).fetchone()

    evaluation = None
    if season and gm:
        evaluation = db.execute(
            "SELECT * FROM gm_season_evaluations WHERE gm_id = %s AND season_id = %s",
            (gm["id"], season["id"]),
        ).fetchone()

    return templates.TemplateResponse(
        request,
        "history/season.html",
        {
            "league_id": league_id,
            "year": year,
            "season": dict(season) if season else None,
            "gm_evaluation": dict(evaluation) if evaluation else None,
            "standings": [],
            "stat_leaders": {},
            "win_trend": [],
        },
    )
