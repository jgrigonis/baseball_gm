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

import sqlite3
import uuid
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.api.database import get_db
from src.api.schemas import player_row_to_grades, skill_to_grade
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_skills import PlayerSkills, SKILLS

router = APIRouter(tags=["web"])
templates = Jinja2Templates(directory="src/web/templates")

DB = Annotated[sqlite3.Connection, Depends(get_db)]



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
    c_rating  = ratings.get("c", 0)
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

    pitching_section = {"section": "Pitching", "skills": [
        {"key": "strikes",      "label": "Stuff",       "grade": grades.stuff or g(skills.get("strikes"))},
        {"key": "accuracy",     "label": "Control",     "grade": grades.control or g(skills.get("accuracy"))},
        {"key": "stamina",      "label": "Stamina",     "grade": grades.stamina or g(skills.get("stamina"))},
        {"key": "recovery",     "label": "Recovery",    "grade": grades.recovery or g(skills.get("recovery"))},
        {"key": "ground_balls", "label": "GB tendency", "grade": g(skills.get("ground_balls"))},
        {"key": "sp",           "label": "SP rating",   "grade": rg("sp")},
        {"key": "rp",           "label": "RP rating",   "grade": rg("rp")},
    ]}

    hitting_section = {"section": "Hitting", "skills": [
        {"key": "contact",      "label": "Contact",     "grade": grades.contact or g(skills.get("contact"))},
        {"key": "power",        "label": "Power",       "grade": grades.power or g(skills.get("power"))},
        {"key": "eye",          "label": "Eye",         "grade": grades.eye or g(skills.get("eye"))},
        {"key": "speed",        "label": "Speed",       "grade": grades.speed or g(skills.get("speed"))},
        {"key": "base_running", "label": "Baserunning", "grade": g(skills.get("base_running"))},
        {"key": "bunting",      "label": "Bunting",     "grade": g(skills.get("bunting"))},
        {"key": "lead_off",     "label": "Leadoff",     "grade": rg("lead_off")},
        {"key": "power_hitter", "label": "Power hitter","grade": rg("power_hitter")},
        {"key": "contact_hitter","label":"Contact hitter","grade": rg("contact_hitter")},
    ]}

    defense_section = {"section": "Defense", "skills": [
        {"key": "if",  "label": "Infield (IF)", "grade": rg("if")},
        {"key": "of",  "label": "Outfield (OF)","grade": rg("of")},
        {"key": "c",   "label": "Catcher (CA)", "grade": rg("c")},
        {"key": "1b",  "label": "First base",   "grade": rg("1b")},
        {"key": "arm", "label": "Arm",          "grade": grades.arm or g(skills.get("arm"))},
    ]}

    general_section = {"section": "General", "skills": [
        {"key": "clutch",        "label": "Clutch",        "grade": g(skills.get("clutch"))},
        {"key": "durability",    "label": "Durability",    "grade": g(skills.get("durability"))},
        {"key": "overall_offense","label":"Off. rating",   "grade": rg("overall_offense")},
    ]}

    if grades.player_type == "pitcher":
        return [pitching_section, general_section, defense_section, hitting_section]
    else:
        return [hitting_section, general_section, defense_section, pitching_section]


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


def _resolve_user(db: sqlite3.Connection, token: str | None) -> sqlite3.Row | None:
    """Return the users row for a session cookie, or None."""
    if not token:
        return None
    return db.execute(
        "SELECT * FROM users WHERE session_token = ?", (token,)
    ).fetchone()


def _resolve_gm(
    db: sqlite3.Connection, user_id: str, league_id: str
) -> sqlite3.Row | None:
    """Return the gms row for this user in this league, or None."""
    return db.execute(
        "SELECT * FROM gms WHERE user_id = ? AND league_id = ?",
        (user_id, league_id),
    ).fetchone()



def _draft_is_complete(db, league_id: str) -> bool:
    row = db.execute(
        """SELECT d.state FROM drafts d
           JOIN league_seasons ls ON ls.season_id = d.season_id
           WHERE ls.league_id = ? ORDER BY d.created_at DESC LIMIT 1""",
        (league_id,),
    ).fetchone()
    return bool(row and row["state"] == "complete")

def _tab_visible(state: str) -> list[str]:
    always = ["draft", "standings", "leaders", "roster", "lineup", "strategy"]
    if state == "lobby":                return []
    if state == "draft":               return always
    if state in ("season", "playoffs"): return always + ["schedule"]
    return always


def _shell_ctx(
    request: Request,
    db: sqlite3.Connection,
    league_id: str,
    user: sqlite3.Row,
    gm: sqlite3.Row | None,
    active_tab: str | None = None,
) -> dict:
    league = db.execute("SELECT * FROM leagues WHERE id = ?", (league_id,)).fetchone()
    team = None
    if gm and gm["team_id"]:
        team = db.execute(
            "SELECT city, mascot FROM teams WHERE id = ?", (gm["team_id"],)
        ).fetchone()

    season = db.execute(
        """SELECT s.* FROM seasons s
           JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = ? ORDER BY s.year DESC LIMIT 1""",
        (league_id,),
    ).fetchone()

    return {
                "league_id": league_id,
        "league_name":         league["name"]                if league else "—",
        "league_state":        league["state"]               if league else "lobby",
        "league_mode":         league["mode"]                if league else "blitz",
        "join_code":           league["join_code"]           if league else "",
        "num_teams":           league["num_teams"]           if league else 30,
        "decision_window_sec": league["decision_window_sec"] if league else 120,
        "draft_window_sec":    league["draft_window_sec"]    if league else 300,
        "reentry_enabled":     bool(league["reentry_enabled"]) if league else True,
        "pace_control":        league["pace_control"]        if league else "timer",
        "gm_id":               gm["id"]                     if gm else None,
        "gm_display_name":     gm["display_name"]           if gm else user["display_name"],
        "team_id":             gm["team_id"]                if gm else None,
        "team_name":           f"{team['city']} {team['mascot']}" if team else None,
        "is_commissioner":     (league and gm and league["commissioner_gm_id"] == gm["id"]),
        "active_tab":          active_tab,
        "visible_tabs":        _tab_visible(league["state"] if league else "lobby"),
        "season_id":           season["id"]   if season else None,
        "season_name":         season["name"] if season else None,
        "draft_complete":      _draft_is_complete(db, league_id) if league else False,
    }


def _respond(request: Request, partial_template: str, ctx: dict) -> HTMLResponse:
    """HTMX → return partial only. Direct nav → full shell with partial embedded."""
    if _is_htmx(request):
        return templates.TemplateResponse(request, partial_template, ctx)
    ctx["tab_template"] = partial_template
    return templates.TemplateResponse(request, "dashboard/shell.html", ctx)


# ── Landing / Auth ─────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
def landing(request: Request, db: DB, gm_session: str | None = Cookie(default=None)):
    user = _resolve_user(db, gm_session)
    if user:
        return RedirectResponse("/leagues/")
    return templates.TemplateResponse(request, "landing.html", {})


@router.post("/auth/guest")
def create_guest(
    request: Request, db: DB,
    display_name: str = Form(default="Guest"),
):
    """
    Create a guest identity (users row only).
    If a valid session cookie already exists, reuse that user rather than
    creating a new one — prevents identity fragmentation on repeat visits.
    """
    # Reuse existing session if the cookie is still valid
    existing_token = request.cookies.get("gm_session")
    if existing_token:
        existing = db.execute(
            "SELECT * FROM users WHERE session_token = ?", (existing_token,)
        ).fetchone()
        if existing:
            return RedirectResponse("/leagues/", status_code=302)

    token = uuid.uuid4().hex + uuid.uuid4().hex
    user_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO users (id, session_token, display_name) VALUES (?, ?, ?)",
        (user_id, token, display_name or "Guest"),
    )
    db.commit()
    resp = RedirectResponse("/leagues/", status_code=302)
    resp.set_cookie(
        "gm_session", token,
        max_age=60 * 60 * 24 * 365 * 5,
        httponly=True, samesite="lax",
    )
    return resp


@router.post("/auth/reclaim/{league_id}")
def reclaim_league(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    """
    Reassign a league's gm.user_id to the current session's user.
    Used when a guest has lost their cookie and wants to reconnect.
    """
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/", status_code=302)

    # Find the gm row for this league that has the same display name
    gm = db.execute(
        """SELECT g.id FROM gms g
           JOIN users u ON u.id = g.user_id
           WHERE g.league_id = ? AND u.display_name = ? AND g.is_ai = 0
           LIMIT 1""",
        (league_id, user["display_name"]),
    ).fetchone()

    if gm:
        db.execute(
            "UPDATE gms SET user_id = ? WHERE id = ?",
            (user["id"], gm["id"]),
        )
        db.commit()

    return RedirectResponse(f"/leagues/{league_id}/", status_code=302)


@router.post("/auth/logout")
def logout():
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie("gm_session")
    return resp


# ── League list ────────────────────────────────────────────────────────────────

@router.get("/leagues/", response_class=HTMLResponse)
def leagues_index(
    request: Request, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/")

    # Auto-reclaim: any gm row with same display_name but different user_id
    # gets reassigned to the current user. This handles the common case where
    # the browser cookie was cleared and a new guest identity was created.
    db.execute(
        """UPDATE gms SET user_id = ?
           WHERE is_ai = 0
             AND user_id != ?
             AND user_id IN (
               SELECT id FROM users WHERE display_name = ?
             )""",
        (user["id"], user["id"], user["display_name"]),
    )
    db.commit()

    rows = db.execute(
        """SELECT l.* FROM leagues l
           JOIN gms g ON g.league_id = l.id
           WHERE g.user_id = ? AND g.is_ai = 0
           ORDER BY l.created_at DESC""",
        (user["id"],),
    ).fetchall()

    return templates.TemplateResponse(request, "leagues/index.html", {
        "user": dict(user),
        "leagues": [dict(r) for r in rows],
    })


@router.get("/leagues/new", response_class=HTMLResponse)
def new_league_page(request: Request):
    return templates.TemplateResponse(request, "leagues/new.html", {})


@router.post("/leagues/new")
def create_league(
    request: Request, db: DB,
    gm_session: str | None = Cookie(default=None),
    name: str = Form(...),
    mode: str = Form("blitz"),
    decision_window_sec: int = Form(120),
    draft_window_sec: int = Form(300),
    reentry_enabled: bool = Form(True),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/", status_code=302)

    import random as _random, string as _string, uuid as _uuid

    league_id = str(_uuid.uuid4())
    gm_id = str(_uuid.uuid4())
    join_code = "".join(_random.choices(_string.ascii_uppercase + _string.digits, k=6))

    db.execute(
        """INSERT INTO leagues
             (id, name, join_code, mode, num_teams, decision_window_sec,
              draft_window_sec, reentry_enabled, pace_control, state)
           VALUES (?, ?, ?, ?, 30, ?, ?, ?, 'timer', 'lobby')""",
        (league_id, name, join_code, mode, decision_window_sec,
         draft_window_sec, int(reentry_enabled)),
    )
    db.execute(
        "INSERT INTO gms (id, league_id, user_id, display_name, is_ai) VALUES (?, ?, ?, ?, 0)",
        (gm_id, league_id, user["id"], user["display_name"]),
    )
    db.execute("INSERT INTO gm_profiles (gm_id) VALUES (?)", (gm_id,))
    db.execute("UPDATE leagues SET commissioner_gm_id = ? WHERE id = ?", (gm_id, league_id))
    db.commit()

    return RedirectResponse(f"/leagues/{league_id}/", status_code=302)


@router.post("/leagues/join")
def join_league(
    request: Request, db: DB,
    gm_session: str | None = Cookie(default=None),
    join_code: str = Form(...),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/", status_code=302)

    import uuid as _uuid

    league = db.execute(
        "SELECT * FROM leagues WHERE join_code = ?", (join_code.upper(),)
    ).fetchone()
    if not league:
        return templates.TemplateResponse(request, "leagues/join.html", {"error": "League not found."})
    if league["state"] != "lobby":
        return templates.TemplateResponse(request, "leagues/join.html", {"error": "League has already started."})

    # Check if already a member
    existing = db.execute(
        "SELECT id FROM gms WHERE league_id = ? AND user_id = ?",
        (league["id"], user["id"]),
    ).fetchone()
    if existing:
        return RedirectResponse(f"/leagues/{league['id']}/", status_code=302)

    gm_id = str(_uuid.uuid4())
    db.execute(
        "INSERT INTO gms (id, league_id, user_id, display_name, is_ai) VALUES (?, ?, ?, ?, 0)",
        (gm_id, league["id"], user["id"], user["display_name"]),
    )
    db.execute("INSERT INTO gm_profiles (gm_id) VALUES (?)", (gm_id,))
    db.commit()

    return RedirectResponse(f"/leagues/{league['id']}/", status_code=302)


@router.get("/leagues/join", response_class=HTMLResponse)
def join_page(request: Request):
    return templates.TemplateResponse(request, "leagues/join.html", {})


# ── League actions ────────────────────────────────────────────────────────────

@router.post("/leagues/{league_id}/start")
def start_league(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/", status_code=302)

    gm = _resolve_gm(db, user["id"], league_id)
    if not gm:
        return RedirectResponse(f"/leagues/{league_id}/", status_code=302)

    league = db.execute("SELECT * FROM leagues WHERE id = ?", (league_id,)).fetchone()
    if not league or league["commissioner_gm_id"] != gm["id"]:
        return RedirectResponse(f"/leagues/{league_id}/", status_code=302)

    from src.api.services.league_start import start_league as _start
    import traceback
    try:
        _start(league_id, db)
    except Exception as e:
        # Surface the error as a plain response so we can see what went wrong
        return HTMLResponse(
            f"<pre style='font-family:monospace;padding:24px;background:#0c0f1a;color:#ef4444;'>"
            f"Start league failed:\n\n{traceback.format_exc()}</pre>",
            status_code=500,
        )

    return RedirectResponse(f"/leagues/{league_id}/", status_code=302)



# ── Draft actions ──────────────────────────────────────────────────────────────

@router.put("/leagues/{league_id}/draft/preferences")
async def save_draft_preferences(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    """
    Save the GM's draft preference list. Called from JS using the session
    cookie — no token exposure needed. Proxies to the existing draft logic.
    """
    from fastapi.responses import JSONResponse

    user = _resolve_user(db, gm_session)
    if not user:
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    gm = _resolve_gm(db, user["id"], league_id)
    if not gm:
        return JSONResponse({"detail": "Not a member of this league"}, status_code=403)

    # Find the current draft for this league
    draft = db.execute(
        """SELECT d.* FROM drafts d
           JOIN league_seasons ls ON ls.season_id = d.season_id
           WHERE ls.league_id = ? ORDER BY d.created_at DESC LIMIT 1""",
        (league_id,),
    ).fetchone()
    if not draft:
        return JSONResponse({"detail": "No draft found"}, status_code=404)
    if draft["state"] == "complete":
        return JSONResponse({"detail": "Draft is already complete"}, status_code=409)

    body = await request.json()
    player_ids = body.get("player_ids", [])
    if not player_ids:
        return JSONResponse({"detail": "player_ids required"}, status_code=422)

    # Validate all IDs exist
    for pid in player_ids:
        if not db.execute("SELECT 1 FROM players WHERE id = ?", (pid,)).fetchone():
            return JSONResponse({"detail": f"Unknown player: {pid}"}, status_code=422)

    # Replace existing preferences atomically
    db.execute(
        "DELETE FROM draft_preferences WHERE gm_id = ? AND draft_id = ?",
        (gm["id"], draft["id"]),
    )
    db.executemany(
        "INSERT INTO draft_preferences (gm_id, draft_id, player_id, rank) VALUES (?, ?, ?, ?)",
        [(gm["id"], draft["id"], pid, rank + 1) for rank, pid in enumerate(player_ids)],
    )
    db.commit()

    return JSONResponse({"saved": len(player_ids)})

# ── Dashboard shell ────────────────────────────────────────────────────────────

@router.get("/leagues/{league_id}/", response_class=HTMLResponse)
def dashboard(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/")

    league = db.execute("SELECT * FROM leagues WHERE id = ?", (league_id,)).fetchone()
    if not league:
        return RedirectResponse("/leagues/")

    gm = _resolve_gm(db, user["id"], league_id)
    state = league["state"]

    if state == "lobby":
        return _lobby(request, league_id, db, user, gm)
    if state == "draft":
        return RedirectResponse(f"/leagues/{league_id}/draft")
    if state in ("season", "playoffs"):
        return RedirectResponse(f"/leagues/{league_id}/standings")
    if state == "evaluation":
        season = db.execute(
            """SELECT s.year FROM seasons s JOIN league_seasons ls
               ON ls.season_id = s.id WHERE ls.league_id = ?
               ORDER BY s.year DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
        year = season["year"] if season else 1
        return RedirectResponse(f"/leagues/{league_id}/history/{year}/")
    return RedirectResponse(f"/leagues/{league_id}/standings")


def _lobby(request, league_id, db, user, gm):
    league = db.execute("SELECT * FROM leagues WHERE id = ?", (league_id,)).fetchone()
    gms = db.execute(
        """SELECT g.id, g.display_name, g.is_ai, g.is_away, g.team_id,
                  t.city, t.mascot
           FROM gms g LEFT JOIN teams t ON t.id = g.team_id
           WHERE g.league_id = ? ORDER BY g.created_at""",
        (league_id,),
    ).fetchall()
    return templates.TemplateResponse(request, "dashboard/lobby.html", {
        "league_id":           league_id,
        "league_name":         league["name"],
        "league_state":        "lobby",
        "join_code":           league["join_code"],
        "num_teams":           league["num_teams"],
        "decision_window_sec": league["decision_window_sec"],
        "draft_window_sec":    (dict(league).get("draft_window_sec") or 300),
        "reentry_enabled":     bool(league["reentry_enabled"]),
        "pace_control":        league["pace_control"],
        "league_mode":         league["mode"],
        "gm_display_name":     gm["display_name"] if gm else user["display_name"],
        "current_gm_id":       gm["id"] if gm else None,
        "is_commissioner":     gm and league["commissioner_gm_id"] == gm["id"],
        "draft_complete":      False,
        "visible_tabs":        [],
        "gms": [dict(r) for r in gms],
    })


# ── Tab: Draft ─────────────────────────────────────────────────────────────────

@router.get("/leagues/{league_id}/draft", response_class=HTMLResponse)
def draft_tab(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/")

    gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, league_id, user, gm, "draft")

    draft = db.execute(
        """SELECT d.* FROM drafts d
           JOIN league_seasons ls ON ls.season_id = d.season_id
           WHERE ls.league_id = ? ORDER BY d.created_at DESC LIMIT 1""",
        (league_id,),
    ).fetchone()

    if draft:
        picked_ids = {
            r["player_id"] for r in db.execute(
                "SELECT player_id FROM draft_picks WHERE draft_id = ?",
                (draft["id"],),
            ).fetchall()
        }
        # Scope board strictly to players belonging to this league.
        # league_id is set by DraftGenerator when prospects are created.
        all_players = db.execute(
            """SELECT p.*, ps.status FROM players p
               JOIN player_status ps ON ps.player_id = p.id
               WHERE ps.status IN ('free_agent', 'unassigned', 'prospect')
               AND p.league_id = ?
               ORDER BY p.last_name, p.first_name""",
            (league_id,),
        ).fetchall()

        board = []
        for row in all_players:
            if row["id"] in picked_ids:
                continue
            skills_row = db.execute(
                "SELECT * FROM player_skills WHERE player_id = ?", (row["id"],)
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
            board.append(g)

        prefs = []
        if gm:
            prefs = db.execute(
                """SELECT dp.player_id FROM draft_preferences dp
                   WHERE dp.draft_id = ? AND dp.gm_id = ?
                   ORDER BY dp.rank""",
                (draft["id"], gm["id"]),
            ).fetchall()

        ctx["draft_id"]    = draft["id"]
        ctx["board"]       = board
        ctx["preferences"] = [r["player_id"] for r in prefs]
    else:
        ctx["draft_id"]    = None
        ctx["board"]       = []
        ctx["preferences"] = []

    # Load GM's current roster for the right-hand column
    players = []
    if gm and gm["team_id"]:
        roster_rows = db.execute(
            """SELECT p.*, ps.status
               FROM players p
               JOIN team_players tp ON tp.player_id = p.id AND tp.team_id = ?
               JOIN player_status ps ON ps.player_id = p.id
               ORDER BY ps.status, p.last_name""",
            (gm["team_id"],),
        ).fetchall()
        for row in roster_rows:
            d = dict(row)
            skills_row = db.execute(
                "SELECT * FROM player_skills WHERE player_id = ?", (d["id"],)
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
            players.append(g)
    ctx["players"] = players

    return _respond(request, "dashboard/partials/draft.html", ctx)



@router.post("/leagues/{league_id}/draft/execute")
def execute_draft(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    """Execute the blitz auto-draft and redirect to results."""
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/", status_code=302)

    gm = _resolve_gm(db, user["id"], league_id)
    if not gm:
        return RedirectResponse(f"/leagues/{league_id}/draft", status_code=302)

    draft = db.execute(
        """SELECT d.* FROM drafts d
           JOIN league_seasons ls ON ls.season_id = d.season_id
           WHERE ls.league_id = ? ORDER BY d.created_at DESC LIMIT 1""",
        (league_id,),
    ).fetchone()

    if not draft:
        return RedirectResponse(f"/leagues/{league_id}/draft", status_code=302)

    # If already complete, just go to results
    if draft["state"] == "complete":
        return RedirectResponse(f"/leagues/{league_id}/draft/results", status_code=302)

    import traceback
    try:
        from src.api.services.draft_execute import execute_blitz_draft
        execute_blitz_draft(draft["id"], db)
    except Exception as e:
        return HTMLResponse(
            f"<pre style='font-family:monospace;padding:24px;background:#0c0f1a;color:#ef4444;'>"
            f"Draft execution failed:\n\n{traceback.format_exc()}</pre>",
            status_code=500,
        )

    return RedirectResponse(f"/leagues/{league_id}/draft/results", status_code=302)


@router.get("/leagues/{league_id}/draft/results", response_class=HTMLResponse)
def draft_results(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    """Show completed draft results — all picks by round, your picks highlighted."""
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/")

    gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, league_id, user, gm, "draft")

    draft = db.execute(
        """SELECT d.* FROM drafts d
           JOIN league_seasons ls ON ls.season_id = d.season_id
           WHERE ls.league_id = ? ORDER BY d.created_at DESC LIMIT 1""",
        (league_id,),
    ).fetchone()

    rounds = []
    my_team_id = gm["team_id"] if gm else None

    if draft:
        picks = db.execute(
            """SELECT dp.round, dp.pick_number, dp.team_id, dp.player_id, dp.auto_picked,
                      p.first_name, p.last_name, p.position,
                      t.city, t.mascot
               FROM draft_picks dp
               JOIN players p ON p.id = dp.player_id
               JOIN teams t ON t.id = dp.team_id
               WHERE dp.draft_id = ?
               ORDER BY dp.pick_number""",
            (draft["id"],),
        ).fetchall()

        human_team_ids = {
            r["team_id"] for r in db.execute(
                "SELECT team_id FROM gms WHERE league_id = ? AND is_ai = 0 AND team_id IS NOT NULL",
                (league_id,),
            ).fetchall()
        }

        # Group by round
        rounds_map = {}
        for pick in picks:
            r = pick["round"]
            if r not in rounds_map:
                rounds_map[r] = []
            is_mine   = pick["team_id"] == my_team_id
            is_human  = pick["team_id"] in human_team_ids and not is_mine
            rounds_map[r].append({
                "pick_number": pick["pick_number"],
                "team_id":     pick["team_id"],
                "player_id":   pick["player_id"],
                "team_name":   f"{pick['city']} {pick['mascot']}",
                "player_name": f"{pick['first_name']} {pick['last_name']}",
                "position":    pick["position"] or "?",
                "auto_picked": bool(pick["auto_picked"]),
                "is_mine":     is_mine,
                "is_human":    is_human,
            })
        rounds = [{"round": r, "picks": picks}
                  for r, picks in sorted(rounds_map.items())]

    ctx["rounds"]     = rounds
    ctx["draft_done"] = bool(draft and draft["state"] == "complete")
    return _respond(request, "dashboard/partials/draft_results.html", ctx)


@router.post("/leagues/{league_id}/roster/save", response_class=HTMLResponse)
def save_roster(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    """Save 40-man roster. Enforces the 40-player limit."""
    from fastapi import Form as _Form
    import json as _json

    user = _resolve_user(db, gm_session)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    gm = _resolve_gm(db, user["id"], league_id)
    if not gm or not gm["team_id"]:
        return HTMLResponse("No team", status_code=400)

    # Read JSON body
    import asyncio
    body_bytes = asyncio.get_event_loop().run_until_complete(request.body())         if hasattr(request, '_body') else None

    return HTMLResponse("ok")  # placeholder — real logic below


@router.put("/leagues/{league_id}/roster/save")
def save_roster_put(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    """PUT endpoint for roster save from JS fetch."""
    from fastapi.responses import JSONResponse
    import asyncio

    user = _resolve_user(db, gm_session)
    if not user:
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    gm = _resolve_gm(db, user["id"], league_id)
    if not gm or not gm["team_id"]:
        return JSONResponse({"detail": "No team"}, status_code=400)

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
            {"detail": f"40-man roster cannot exceed 40 players ({len(forty_man_ids)} submitted)"},
            status_code=422,
        )

    # Verify all submitted players belong to this team
    team_player_ids = {
        r["player_id"] for r in db.execute(
            "SELECT player_id FROM team_players WHERE team_id = ?", (team_id,)
        ).fetchall()
    }
    for pid in forty_man_ids:
        if pid not in team_player_ids:
            return JSONResponse({"detail": f"Player {pid} not on this team"}, status_code=422)

    forty_set = set(forty_man_ids)

    # Update statuses
    for pid in team_player_ids:
        new_status = "40man" if pid in forty_set else "minors"
        existing = db.execute(
            "SELECT status FROM player_status WHERE player_id = ?", (pid,)
        ).fetchone()
        if existing:
            db.execute(
                "UPDATE player_status SET status = ? WHERE player_id = ?",
                (new_status, pid),
            )
        else:
            db.execute(
                "INSERT INTO player_status (player_id, status, since) VALUES (?, ?, datetime('now'))",
                (pid, new_status),
            )

    db.commit()
    return JSONResponse({"saved": len(forty_man_ids)})

# ── Tab: Standings ─────────────────────────────────────────────────────────────

@router.get("/leagues/{league_id}/standings", response_class=HTMLResponse)
def standings(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/")

    gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, league_id, user, gm, "standings")
    season_id = ctx["season_id"]
    teams = []

    if season_id:
        rows = db.execute(
            """SELECT
                 t.id as team_id, t.city, t.mascot,
                 SUM(tgs.win)  as wins,
                 SUM(tgs.loss) as losses,
                 SUM(tgs.runs) as runs_scored
               FROM teams t
               JOIN league_season_teams lst
                 ON lst.team_id = t.id
                 AND lst.league_id = ?
                 AND lst.season_id = ?
               JOIN team_game_stats tgs ON tgs.team_id = t.id
               JOIN games g
                 ON g.id = tgs.game_id
                 AND g.season_id = ?
                 AND g.completed = 1
               GROUP BY t.id
               ORDER BY wins DESC, losses ASC""",
            (league_id, season_id, season_id),
        ).fetchall()

        ra_rows = db.execute(
            """SELECT tgs.team_id, SUM(opp.runs) as runs_allowed
               FROM team_game_stats tgs
               JOIN games g ON g.id = tgs.game_id AND g.season_id = ? AND g.completed = 1
               JOIN team_game_stats opp
                 ON opp.game_id = g.id AND opp.team_id != tgs.team_id
               GROUP BY tgs.team_id""",
            (season_id,),
        ).fetchall()
        ra_map = {r["team_id"]: r["runs_allowed"] or 0 for r in ra_rows}

        human_team_ids = {
            r["team_id"] for r in db.execute(
                "SELECT team_id FROM gms WHERE league_id = ? AND is_ai = 0 AND team_id IS NOT NULL",
                (league_id,),
            ).fetchall()
        }

        for r in rows:
            wins   = r["wins"]        or 0
            losses = r["losses"]      or 0
            rs     = r["runs_scored"] or 0
            ra     = ra_map.get(r["team_id"], 0)
            teams.append({
                "team_id":      r["team_id"],
                "city":         r["city"],
                "mascot":       r["mascot"],
                "wins":         wins,
                "losses":       losses,
                "run_diff":     rs - ra,
                "runs_scored":  rs,
                "runs_allowed": ra,
                "is_human":     r["team_id"] in human_team_ids,
                "last_10":      None,
                "streak":       None,
            })

    ctx["teams"]        = teams
    ctx["games_played"] = sum(t["wins"] + t["losses"] for t in teams) // 2 if teams else 0
    return _respond(request, "dashboard/partials/standings.html", ctx)


# ── Tab: Leaders ───────────────────────────────────────────────────────────────

@router.get("/leagues/{league_id}/leaders", response_class=HTMLResponse)
def leaders(
    request: Request, league_id: str, db: DB,
    category: str = "batting",
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/")

    gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, league_id, user, gm, "leaders")
    ctx["category"] = category
    ctx["rows"]     = []
    return _respond(request, "dashboard/partials/leaders.html", ctx)


# ── Tab: Roster ────────────────────────────────────────────────────────────────

@router.get("/leagues/{league_id}/roster", response_class=HTMLResponse)
def roster(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/")

    gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, league_id, user, gm, "roster")
    players = []

    if gm and gm["team_id"]:
        rows = db.execute(
            """SELECT p.*, ps.status
               FROM players p
               JOIN team_players tp ON tp.player_id = p.id AND tp.team_id = ?
               JOIN player_status ps ON ps.player_id = p.id
               ORDER BY ps.status, p.last_name""",
            (gm["team_id"],),
        ).fetchall()
        for row in rows:
            d = dict(row)
            skills_row = db.execute(
                "SELECT * FROM player_skills WHERE player_id = ?", (d["id"],)
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
            players.append(g)

    ctx["players"] = players
    return _respond(request, "dashboard/partials/roster.html", ctx)


# ── Tab: Lineup ────────────────────────────────────────────────────────────────

@router.get("/leagues/{league_id}/lineup", response_class=HTMLResponse)
def lineup(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/")

    gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, league_id, user, gm, "lineup")
    ctx["batting_order"] = []
    ctx["bench"]         = []
    ctx["rotation"]      = []
    ctx["bullpen"]       = []
    return _respond(request, "dashboard/partials/lineup.html", ctx)


# ── Tab: Strategy ──────────────────────────────────────────────────────────────

@router.get("/leagues/{league_id}/strategy", response_class=HTMLResponse)
def strategy(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/")

    gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, league_id, user, gm, "strategy")

    profile_row = db.execute(
        "SELECT * FROM gm_profiles WHERE gm_id = ?", (gm["id"],)
    ).fetchone() if gm else None

    _L = ["traditional", "analytics", "speed-first", "power-first"]
    _S = ["conservative", "standard", "aggressive"]
    _B = ["never", "situational", "frequent"]
    _P = ["none", "vs-handedness", "aggressive"]
    _U = ["let-them-work", "pitch-count-strict", "matchup-based"]
    _C = ["saves-only", "high-leverage", "best-available"]
    _N = ["deep-pen", "starter-heavy"]

    def idx(lst, val, default=0):
        try:    return lst.index(val)
        except: return default

    if profile_row:
        p = dict(profile_row)
        ctx["profile"] = {
            "lineup_style_index":     idx(_L, p.get("lineup_style",     "analytics"),         1),
            "steal_aggression_index": idx(_S, p.get("steal_aggression", "standard"),           1),
            "sac_bunt_index":         idx(_B, p.get("sac_bunt",         "situational"),        1),
            "platoon_usage_index":    idx(_P, p.get("platoon_usage",    "none"),               0),
            "starter_usage_index":    idx(_U, p.get("starter_usage",    "pitch-count-strict"), 1),
            "closer_usage_index":     idx(_C, p.get("closer_usage",     "saves-only"),         0),
            "bullpen_pref_index":     idx(_N, p.get("bullpen_pref",     "deep-pen"),           0),
        }
    else:
        ctx["profile"] = {
            "lineup_style_index": 1, "steal_aggression_index": 1,
            "sac_bunt_index": 1,     "platoon_usage_index": 0,
            "starter_usage_index": 1,"closer_usage_index": 0,
            "bullpen_pref_index": 0,
        }

    return _respond(request, "dashboard/partials/strategy.html", ctx)


@router.post("/leagues/{league_id}/strategy")
async def save_strategy(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    gm = _resolve_gm(db, user["id"], league_id)
    if not gm:
        return HTMLResponse("Not a member of this league", status_code=403)

    form = await request.form()
    _MAPS = {
        "lineup_style":     ["traditional", "analytics", "speed-first", "power-first"],
        "steal_aggression": ["conservative", "standard", "aggressive"],
        "sac_bunt":         ["never", "situational", "frequent"],
        "platoon_usage":    ["none", "vs-handedness", "aggressive"],
        "starter_usage":    ["let-them-work", "pitch-count-strict", "matchup-based"],
        "closer_usage":     ["saves-only", "high-leverage", "best-available"],
        "bullpen_pref":     ["deep-pen", "starter-heavy"],
    }
    updates = {}
    for field, options in _MAPS.items():
        i = int(form.get(field, 0))
        updates[field] = options[min(i, len(options) - 1)]

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    db.execute(
        f"UPDATE gm_profiles SET {set_clause}, updated_at = datetime('now') WHERE gm_id = ?",
        [*updates.values(), gm["id"]],
    )
    db.commit()
    return HTMLResponse(
        '<span style="color:var(--green);font-family:var(--font-mono);font-size:11px;">✓ Saved</span>'
    )


# ── Tab: Schedule ──────────────────────────────────────────────────────────────

@router.get("/leagues/{league_id}/schedule", response_class=HTMLResponse)
@router.get("/leagues/{league_id}/schedule/{date}", response_class=HTMLResponse)
def schedule(
    request: Request, league_id: str, db: DB,
    date: str | None = None,
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/")

    gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, league_id, user, gm, "schedule")
    season_id = ctx["season_id"]

    if not date and season_id:
        row = db.execute(
            "SELECT MAX(game_date) as d FROM games WHERE season_id = ? AND completed = 1",
            (season_id,),
        ).fetchone()
        date = row["d"] if row else None

    games = []
    prev_date = next_date = None

    if date and season_id:
        rows = db.execute(
            """SELECT g.id, g.home_team_id, g.away_team_id,
                      g.home_score, g.away_score, g.innings_played, g.winner_id,
                      ht.city as home_city, ht.mascot as home_mascot,
                      at.city as away_city, at.mascot as away_mascot
               FROM games g
               JOIN teams ht ON ht.id = g.home_team_id
               JOIN teams at ON at.id = g.away_team_id
               WHERE g.season_id = ? AND g.game_date = ?
               ORDER BY g.home_team_id""",
            (season_id, date),
        ).fetchall()
        games = [dict(r) for r in rows]

        prev = db.execute(
            "SELECT MAX(game_date) as d FROM games WHERE season_id = ? AND game_date < ? AND completed = 1",
            (season_id, date),
        ).fetchone()
        nxt = db.execute(
            "SELECT MIN(game_date) as d FROM games WHERE season_id = ? AND game_date > ? AND completed = 1",
            (season_id, date),
        ).fetchone()
        prev_date = prev["d"] if prev else None
        next_date = nxt["d"] if nxt else None

    ctx["game_date"] = date
    ctx["games"]     = games
    ctx["prev_date"] = prev_date
    ctx["next_date"] = next_date
    return _respond(request, "dashboard/partials/schedule.html", ctx)


# ── Game detail ────────────────────────────────────────────────────────────────

@router.get("/leagues/{league_id}/games/{game_id}", response_class=HTMLResponse)
def game_detail(
    request: Request, league_id: str, game_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/")

    gm = _resolve_gm(db, user["id"], league_id)
    ctx = _shell_ctx(request, db, league_id, user, gm, "schedule")
    game = db.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    ctx["game"]         = dict(game) if game else None
    ctx["tab_template"] = "dashboard/partials/game_detail.html"
    return templates.TemplateResponse(request, "dashboard/shell.html", ctx)


# ── Player panel (slide-in) ────────────────────────────────────────────────────

@router.get("/leagues/{league_id}/players/{player_id}/panel", response_class=HTMLResponse)
def player_panel(
    request: Request, league_id: str, player_id: str, db: DB,
    compare: str | None = None,
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return HTMLResponse("Unauthorized", status_code=401)

    gm = _resolve_gm(db, user["id"], league_id)

    def _load(pid: str) -> dict | None:
        p = db.execute("SELECT * FROM players WHERE id = ?", (pid,)).fetchone()
        if not p:
            return None
        sk  = db.execute("SELECT * FROM player_skills WHERE player_id = ?", (pid,)).fetchone()
        st  = db.execute("SELECT status FROM player_status WHERE player_id = ?", (pid,)).fetchone()
        en  = db.execute("SELECT * FROM player_energy WHERE player_id = ?", (pid,)).fetchone()
        inj = db.execute(
            "SELECT * FROM player_injury_log WHERE player_id = ? ORDER BY injury_date DESC LIMIT 5",
            (pid,),
        ).fetchall()
        team = db.execute(
            """SELECT t.city, t.mascot FROM teams t
               JOIN team_players tp ON tp.team_id = t.id WHERE tp.player_id = ?""",
            (pid,),
        ).fetchone()

        skills = dict(sk) if sk else {}
        grades = player_row_to_grades(dict(p), skills, st["status"] if st else "unassigned")
        ratings = _compute_ratings(skills, dict(p).get("throws", "R"))

        # Overall: prospect rating for undrafted, position-aware rating for rostered
        status = st["status"] if st else "unassigned"
        if status in ("prospect", "unassigned", "free_agent"):
            overall_grade = skill_to_grade(ratings.get("prospect")) if ratings else grades.overall
        elif grades.player_type == "pitcher":
            # Pitchers: best of SP/RP rating — overall_player is offense-based and useless
            best_p = max(ratings.get("sp", 0), ratings.get("rp", 0)) if ratings else 0
            overall_grade = skill_to_grade(best_p) if best_p else grades.overall
        else:
            overall_grade = skill_to_grade(ratings.get("overall_player")) if ratings else grades.overall

        grade_map = _ratings_to_grade_map(grades, skills, ratings)

        # Best defensive grade for card display
        best_def_grade = skill_to_grade(ratings.get("best_def")) if ratings else "?"
        best_def_label = ratings.get("best_def_label", "DEF") if ratings else "DEF"

        energy = None
        if en:
            energy = {
                "current":             round(en["current_energy"] * 100),
                "max":                 round(en["max_energy"] * 100),
                "consecutive_days":    en["consecutive_days"],
                "last_game_date":      en["last_game_date"],
                "season_games_played": en["season_games_played"],
            }

        return {
            **grades.model_dump(),
            "player_id":      pid,
            "team_city":      team["city"]   if team else "—",
            "team_mascot":    team["mascot"] if team else "",
            "grades":         grade_map,
            "overall_grade":  overall_grade,
            "best_def_grade": best_def_grade,
            "best_def_label": best_def_label,
            "energy":         energy,
            "injury_log":     [dict(r) for r in inj],
            "stats":          None,
        }

    ctx = _shell_ctx(request, db, league_id, user, gm)
    ctx["player"]         = _load(player_id)
    ctx["compare_player"] = _load(compare) if compare else None
    return templates.TemplateResponse(request, "dashboard/partials/player_panel.html", ctx)


# ── History ────────────────────────────────────────────────────────────────────

@router.get("/leagues/{league_id}/history/", response_class=HTMLResponse)
def history_index(
    request: Request, league_id: str, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/")

    seasons = db.execute(
        """SELECT s.* FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = ? ORDER BY s.year""",
        (league_id,),
    ).fetchall()

    return templates.TemplateResponse(request, "history/index.html", {
                "league_id": league_id,
        "seasons":   [dict(s) for s in seasons],
    })


@router.get("/leagues/{league_id}/history/{year}/", response_class=HTMLResponse)
def season_summary(
    request: Request, league_id: str, year: int, db: DB,
    gm_session: str | None = Cookie(default=None),
):
    user = _resolve_user(db, gm_session)
    if not user:
        return RedirectResponse("/")

    gm = _resolve_gm(db, user["id"], league_id)

    season = db.execute(
        """SELECT s.* FROM seasons s JOIN league_seasons ls ON ls.season_id = s.id
           WHERE ls.league_id = ? AND s.year = ?""",
        (league_id, year),
    ).fetchone()

    evaluation = None
    if season and gm:
        evaluation = db.execute(
            "SELECT * FROM gm_season_evaluations WHERE gm_id = ? AND season_id = ?",
            (gm["id"], season["id"]),
        ).fetchone()

    return templates.TemplateResponse(request, "history/season.html", {
                "league_id":     league_id,
        "year":          year,
        "season":        dict(season)     if season     else None,
        "gm_evaluation": dict(evaluation) if evaluation else None,
        "standings":     [],
        "stat_leaders":  {},
        "win_trend":     [],
    })
