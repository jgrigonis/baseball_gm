# src/web/router.py
#
# Web frontend routes — render Jinja2 templates.
# Auth via gm_session cookie (stores the same token as X-GM-Session header).
# All DB access uses the same get_db() dependency as the API routers.

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from src.api.dependencies import DB
from src.api.schemas import skill_to_grade, player_row_to_grades
from src.api.dependencies import IsHTMX
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.standings_repo import StandingsRepository
from src.web.utils import tab_response, _shell_ctx
from jinja2 import Environment, FileSystemLoader

# from starlette.responses import HTMLResponse

# Templates are in src/web/templates/ relative to the project root
_TEMPLATES_DIR = Path(__file__).parent / "templates"
# Work around for bug in Jinja2 3.1.6 with Python 3.14 dict hashability change
# _env = Environment(
#     loader=FileSystemLoader(str(_TEMPLATES_DIR)),
#     cache_size=0,
# )
# templates = Jinja2Templates(env=_env)
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)


def render(name: str, context: dict) -> HTMLResponse:
    template = _jinja_env.get_template(name)
    return HTMLResponse(template.render(**context))


router = APIRouter()


# ── Session helpers ───────────────────────────────────────────────────────────
#
# Identity is stored in two cookies:
#   gm_session  — opaque token (UUID hex, persists 5 years)
#   gm_name     — display name chosen at landing
#
# No DB row is created until the user joins or creates a league.
# GM rows are per-league; a single person can have many GM rows across leagues.
# All per-league routes look up the GM row by (user_session, league_id).


def _get_identity(request: Request) -> tuple[str | None, str | None]:
    """Return (session_token, display_name) from cookies, or (None, None)."""
    token = request.cookies.get("gm_session")
    name = request.cookies.get("gm_name")
    return token, name


def _gm_for_league(db, session_token: str | None, league_id: str) -> dict | None:
    """Find the GM row for this session token in a specific league."""
    if not session_token:
        return None
    return db.execute(
        "SELECT * FROM gms WHERE user_session = %s AND league_id = %s",
        (session_token, league_id),
    ).fetchone()


def _require_identity(request: Request):
    """Return (token, name) or (None, redirect)."""
    token, name = _get_identity(request)
    if not token:
        return None, None, RedirectResponse("/", status_code=302)
    return token, name, None


def _require_league_gm(request: Request, league_id: str, db):
    """Return (gm_row, None) or (None, redirect). Used for in-league routes."""
    token, _, redir = _require_identity(request)
    if redir:
        return None, redir
    gm = _gm_for_league(db, token, league_id)
    if not gm:
        # User has identity but isn't a GM in this league
        return None, RedirectResponse("/leagues", status_code=302)
    return gm, None


# ── Landing / Auth ────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def landing(request: Request):
    token, name = _get_identity(request)
    if token and name:
        return RedirectResponse("/leagues", status_code=302)
    return render("landing.html", {"request": request})


@router.post("/auth/guest")
async def create_guest(display_name: str = Form(...)):
    """Store identity in cookies only — no DB row until they join a league."""
    session_token = uuid.uuid4().hex + uuid.uuid4().hex
    resp = RedirectResponse("/leagues", status_code=302)
    resp.set_cookie(
        "gm_session",
        session_token,
        max_age=60 * 60 * 24 * 365 * 5,
        httponly=True,
        samesite="lax",
    )
    resp.set_cookie(
        "gm_name", display_name, max_age=60 * 60 * 24 * 365 * 5, samesite="lax"
    )
    return resp


@router.post("/auth/logout")
async def logout():
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie("gm_session")
    resp.delete_cookie("gm_name")
    return resp


# ── League index ──────────────────────────────────────────────────────────────


@router.get("/leagues", response_class=HTMLResponse)
async def leagues_index(request: Request, db: DB):
    token, name, redir = _require_identity(request)
    if redir:
        return redir

    rows = db.execute(
        """
        SELECT l.id, l.name, l.join_code, l.state, l.mode,
            t.city, t.mascot
        FROM users u
        JOIN gms g ON g.user_id = u.id
        JOIN leagues l ON l.id = g.league_id
        LEFT JOIN teams t ON t.id = g.team_id
        WHERE u.session_token = %s
        ORDER BY l.created_at DESC
    """,
        (token,),
    ).fetchall()

    active = [dict(r) for r in rows if r["state"] != "complete"]
    past = [dict(r) for r in rows if r["state"] == "complete"]

    return render(
        "leagues/index.html",
        {
            "request": request,
            "display_name": name,
            "active_leagues": active,
            "past_leagues": past,
        },
    )


@router.get("/leagues/new", response_class=HTMLResponse)
async def new_league_page(request: Request):
    token, name, redir = _require_identity(request)
    if redir:
        return redir
    return render(
        "leagues/new.html",
        {
            "request": request,
            "display_name": name,
        },
    )


# was create_league
@router.post("/leagues/new")
async def new_league(
    request: Request,
    db: DB,
    name: str = Form(...),
    mode: str = Form("blitz"),
    decision_window_sec: int = Form(120),
):
    token, display_name, redir = _require_identity(request)
    if redir:
        return redir

    import random, string

    league_id = str(uuid.uuid4())
    gm_id = str(uuid.uuid4())
    join_code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))

    db.execute(
        """
        INSERT INTO leagues (id, name, join_code, mode, num_teams, decision_window_sec,
                             reentry_enabled, pace_control, state)
        VALUES (%s, %s, %s, %s, 30, %s, 1, 'timer', 'lobby')
    """,
        (league_id, name, join_code, mode, decision_window_sec),
    )

    db.execute(
        """
        INSERT INTO gms (id, league_id, user_session, display_name, is_ai)
        VALUES (%s, %s, %s, %s, FALSE)
    """,
        (gm_id, league_id, token, display_name or "GM"),
    )

    db.execute(
        "UPDATE leagues SET commissioner_gm_id = %s WHERE id = %s", (gm_id, league_id)
    )
    db.execute(
        "INSERT INTO gm_profiles (gm_id) VALUES (%s) ON CONFLICT DO NOTHING", (gm_id,)
    )
    db.commit()

    return RedirectResponse(f"/leagues/{league_id}/", status_code=302)


@router.get("/leagues/join", response_class=HTMLResponse)
async def join_page(request: Request):
    token, name, redir = _require_identity(request)
    if redir:
        return redir
    return render(
        "leagues/join.html",
        {
            "request": request,
            "display_name": name,
        },
    )


@router.post("/leagues/join")
async def join_league(request: Request, db: DB, join_code: str = Form(...)):
    token, display_name, redir = _require_identity(request)
    if redir:
        return redir

    league = db.execute(
        "SELECT * FROM leagues WHERE join_code = %s", (join_code.upper().strip(),)
    ).fetchone()
    if not league:
        return render(
            "leagues/join.html",
            {
                "request": request,
                "display_name": display_name,
                "error": f"No league found with code '{join_code.upper()}'.",
            },
        )

    existing = db.execute(
        "SELECT id FROM gms WHERE user_session = %s AND league_id = %s",
        (token, league["id"]),
    ).fetchone()
    if not existing:
        gm_id = str(uuid.uuid4())
        db.execute(
            """
            INSERT INTO gms (id, league_id, user_session, display_name, is_ai)
            VALUES (%s, %s, %s, %s, FALSE)
        """,
            (gm_id, league["id"], token, display_name or "GM"),
        )
        db.execute(
            "INSERT INTO gm_profiles (gm_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (gm_id,),
        )
        db.commit()

    return RedirectResponse(f"/leagues/{league['id']}/", status_code=302)


# ── Dashboard shell ───────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/", response_class=HTMLResponse)
async def dashboard(request: Request, league_id: str, db: DB):
    gm, redir = _require_league_gm(request, league_id, db)
    if redir:
        return redir
    lr = LeagueRepository(db)
    league = lr.get_by_id(league_id)
    if not league:
        return RedirectResponse("/leagues", status_code=302)

    state = league["state"]
    if state == "lobby":
        return await _lobby(request, league_id, gm, db)
    if state == "draft":
        return RedirectResponse(f"/leagues/{league_id}/draft", status_code=302)
    if state in ("season", "playoffs"):
        return RedirectResponse(f"/leagues/{league_id}/standings", status_code=302)
    if state == "evaluation":
        year = _current_year(league_id, db)
        return RedirectResponse(
            f"/leagues/{league_id}/history/{year}/", status_code=302
        )
    return RedirectResponse(f"/leagues/{league_id}/standings", status_code=302)


async def _lobby(request: Request, league_id: str, gm: dict, db) -> HTMLResponse:
    lr = LeagueRepository(db)
    league = lr.get_by_id(league_id)
    gms_rows = db.execute(
        """
        SELECT g.id, g.display_name, g.is_ai, g.is_away, g.team_id,
               t.city, t.mascot
        FROM gms g LEFT JOIN teams t ON t.id = g.team_id
        WHERE g.league_id = %s
        ORDER BY g.created_at
    """,
        (league_id,),
    ).fetchall()

    return render(
        "dashboard/lobby.html",
        {
            "request": request,
            "gm_id": gm["id"],
            "league_id": league_id,
            "league_name": league["name"],
            "league_state": league["state"],
            "league_mode": league["mode"],
            "join_code": league["join_code"],
            "num_teams": league["num_teams"],
            "decision_window_sec": league["decision_window_sec"],
            "reentry_enabled": bool(league["reentry_enabled"]),
            "pace_control": league["pace_control"],
            "is_commissioner": league["commissioner_gm_id"] == gm["id"],
            "current_gm_id": gm["id"],
            "gms": [dict(r) for r in gms_rows],
        },
    )


# ── Tab routes ────────────────────────────────────────────────────────────────
# Each route:
#   - Direct load → returns full shell with tab content embedded
#   - HTMX request → returns just the partial (swapped into #tab-content)

# moved to utils
# def _tab_response(request: Request, template_name: str, ctx: dict):
#     if is_htmx(request):
#         return render(template_name, ctx)
#     ctx["tab_template"] = template_name
#     ctx["tab_visible"] = _tab_visible(ctx.get("league_state"))
#     return render("dashboard/shell.html", ctx)


@router.get("/leagues/{league_id}/draft", response_class=HTMLResponse)
async def draft_tab(request: Request, htmx: IsHTMX, league_id: str, db: DB):
    gm, redir = _require_league_gm(request, league_id, db)
    if redir:
        return redir
    ctx = _shell_ctx(request, db, gm, league_id, "draft")

    # Load draft board
    draft = db.execute(
        "SELECT * FROM drafts WHERE league_id = %s ORDER BY created_at DESC LIMIT 1",
        (league_id,),
    ).fetchone()
    ctx["draft"] = dict(draft) if draft else None
    ctx["players"] = []
    if draft:
        ctx["players"] = _load_draft_board(draft["id"], db)

    # Load GM's existing preferences
    ctx["preferences"] = []
    if draft:
        prefs = db.execute(
            """
            SELECT player_id FROM draft_preferences
            WHERE gm_id = %s AND draft_id = %s ORDER BY rank
        """,
            (gm["id"], draft["id"]),
        ).fetchall()
        ctx["preferences"] = [r["player_id"] for r in prefs]

    # Load this GM's current roster (inherited team)
    ctx["roster"] = _load_roster(gm, db)

    return tab_response(request, htmx, "dashboard/partials/draft.html", ctx)


@router.get("/leagues/{league_id}/standings", response_class=HTMLResponse)
async def standings_tab(request: Request, htmx: IsHTMX, league_id: str, db: DB):
    gm, redir = _require_league_gm(request, league_id, db)
    if redir:
        return redir
    ctx = _shell_ctx(request, db, gm, league_id, "standings")
    ctx["teams"] = _load_standings(league_id, db)
    ctx["games_played"] = (
        sum(r["wins"] + r["losses"] for r in ctx["teams"]) // 2 if ctx["teams"] else 0
    )
    ctx["season_name"] = _current_season_name(league_id, db)
    return tab_response(request, htmx, "dashboard/partials/standings.html", ctx)


@router.get("/leagues/{league_id}/roster", response_class=HTMLResponse)
async def roster_tab(request: Request, htmx: IsHTMX, league_id: str, db: DB):
    gm, redir = _require_league_gm(request, league_id, db)
    if redir:
        return redir
    ctx = _shell_ctx(request, db, gm, league_id, "roster")
    ctx["players"] = _load_roster(gm, db)
    ctx["active_count"] = sum(
        1 for p in ctx["players"] if p.get("roster_status") == "26man"
    )
    return tab_response(request, htmx, "dashboard/partials/roster.html", ctx)


@router.get("/leagues/{league_id}/lineup", response_class=HTMLResponse)
async def lineup_tab(request: Request, htmx: IsHTMX, league_id: str, db: DB):
    gm, redir = _require_league_gm(request, league_id, db)
    if redir:
        return redir
    ctx = _shell_ctx(request, db, gm, league_id, "lineup")

    roster = _load_roster(gm, db)
    ctx["hitters"] = [
        p
        for p in roster
        if p.get("player_type") == "hitter" and p.get("roster_status") == "26man"
    ]
    ctx["pitchers"] = [
        p
        for p in roster
        if p.get("player_type") == "pitcher" and p.get("roster_status") == "26man"
    ]

    saved = db.execute(
        """
        SELECT lp.player_id, lp.batting_order, lp.position, lp.is_starter
        FROM gm_lineup_preferences lp
        WHERE lp.gm_id = %s
        ORDER BY lp.batting_order ASC NULLS LAST
    """,
        (gm["id"],),
    ).fetchall()
    ctx["saved_lineup"] = [dict(r) for r in saved]

    return tab_response(request, htmx, "dashboard/partials/lineup.html", ctx)


@router.get("/leagues/{league_id}/strategy", response_class=HTMLResponse)
async def strategy_tab(request: Request, htmx: IsHTMX, league_id: str, db: DB):
    gm, redir = _require_league_gm(request, league_id, db)
    if redir:
        return redir
    ctx = _shell_ctx(request, db, gm, league_id, "strategy")

    profile = db.execute(
        "SELECT * FROM gm_profiles WHERE gm_id = %s", (gm["id"],)
    ).fetchone()

    _INDEX_MAPS = {
        "lineup_style": ["traditional", "analytics", "speed-first", "power-first"],
        "steal_aggression": ["conservative", "standard", "aggressive"],
        "sac_bunt": ["never", "situational", "frequent"],
        "platoon_usage": ["none", "vs-handedness", "aggressive"],
        "starter_usage": ["let-them-work", "pitch-count-strict", "matchup-based"],
        "closer_usage": ["saves-only", "high-leverage", "best-available"],
        "bullpen_pref": ["deep-pen", "starter-heavy"],
    }

    profile_indexes = {}
    if profile:
        for field, options in _INDEX_MAPS.items():
            val = profile[field] if field in profile.keys() else None
            try:
                profile_indexes[f"{field}_index"] = options.index(val)
            except (ValueError, TypeError):
                profile_indexes[f"{field}_index"] = 0

    ctx["profile"] = profile_indexes
    return tab_response(request, htmx, "dashboard/partials/strategy.html", ctx)


@router.post("/leagues/{league_id}/strategy")
async def save_strategy(
    request: Request,
    league_id: str,
    db: DB,
):
    gm, redir = _require_league_gm(request, league_id, db)
    if redir:
        return redir

    form = await request.form()
    _INDEX_MAPS = {
        "lineup_style": ["traditional", "analytics", "speed-first", "power-first"],
        "steal_aggression": ["conservative", "standard", "aggressive"],
        "sac_bunt": ["never", "situational", "frequent"],
        "platoon_usage": ["none", "vs-handedness", "aggressive"],
        "starter_usage": ["let-them-work", "pitch-count-strict", "matchup-based"],
        "closer_usage": ["saves-only", "high-leverage", "best-available"],
        "bullpen_pref": ["deep-pen", "starter-heavy"],
    }
    updates = {}
    for field, options in _INDEX_MAPS.items():
        idx = int(form.get(field, 0))
        updates[field] = options[min(idx, len(options) - 1)]

    set_clause = ", ".join(f"{col} = %s" for col in updates)
    values = list(updates.values()) + [gm["id"]]
    db.execute(
        f"UPDATE gm_profiles SET {set_clause}, updated_at = NOW() WHERE gm_id = %s",
        values,
    )
    db.commit()

    return HTMLResponse(
        '<span style="color:var(--green);font-family:var(--font-mono);font-size:11px;">✓ Saved</span>'
    )


@router.get("/leagues/{league_id}/schedule", response_class=HTMLResponse)
async def schedule_tab(
    request: Request, htmx: IsHTMX, league_id: str, db: DB, date: str | None = None
):
    gm, redir = _require_league_gm(request, league_id, db)
    if redir:
        return redir
    ctx = _shell_ctx(request, db, gm, league_id, "schedule")

    season_id = _current_season_id(league_id, db)
    if not date and season_id:
        # Default to most recent played date
        row = db.execute(
            """
            SELECT game_date FROM games
            WHERE season_id = %s AND completed = 1
            ORDER BY game_date DESC LIMIT 1
        """,
            (season_id,),
        ).fetchone()
        date = row["game_date"] if row else None

    ctx["game_date"] = date
    ctx["games"] = []
    ctx["prev_date"] = None
    ctx["next_date"] = None

    if date and season_id:
        games = db.execute(
            """
            SELECT g.id, g.home_team_id, g.away_team_id,
                   g.home_score, g.away_score, g.innings_played,
                   ht.city || ' ' || ht.mascot as home_team,
                   at.city || ' ' || at.mascot as away_team
            FROM games g
            JOIN teams ht ON ht.id = g.home_team_id
            JOIN teams at ON at.id = g.away_team_id
            WHERE g.season_id = %s AND g.game_date = %s AND g.completed = 1
            ORDER BY ht.city
        """,
            (season_id, date),
        ).fetchall()
        ctx["games"] = [dict(r) for r in games]

        # Prev/next navigation
        prev = db.execute(
            """
            SELECT game_date FROM games
            WHERE season_id = %s AND completed = 1 AND game_date::date < %s
            ORDER BY game_date DESC LIMIT 1
        """,
            (season_id, date),
        ).fetchone()
        nxt = db.execute(
            """
            SELECT game_date FROM games
            WHERE season_id = %s AND completed = 1 AND game_date::date > %s
            ORDER BY game_date ASC LIMIT 1
        """,
            (season_id, date),
        ).fetchone()
        ctx["prev_date"] = prev["game_date"] if prev else None
        ctx["next_date"] = nxt["game_date"] if nxt else None

    return tab_response(request, htmx, "dashboard/partials/schedule.html", ctx)


@router.get("/leagues/{league_id}/schedule/{date}", response_class=HTMLResponse)
async def schedule_date(request: Request, league_id: str, date: str, db: DB):
    return await schedule_tab(request, league_id, db, date=date)


@router.get("/leagues/{league_id}/games/{game_id}", response_class=HTMLResponse)
async def game_detail(
    request: Request, htmx: IsHTMX, league_id: str, game_id: str, db: DB
):
    gm, redir = _require_league_gm(request, league_id, db)
    if redir:
        return redir
    ctx = _shell_ctx(request, db, gm, league_id, "schedule")

    game = db.execute(
        """
        SELECT g.*, ht.city || ' ' || ht.mascot as home_team,
               at.city || ' ' || at.mascot as away_team
        FROM games g
        JOIN teams ht ON ht.id = g.home_team_id
        JOIN teams at ON at.id = g.away_team_id
        WHERE g.id = %s
    """,
        (game_id,),
    ).fetchone()
    ctx["game"] = dict(game) if game else None

    # Box score
    if game:
        batting = db.execute(
            """
            SELECT pgs.*, p.first_name, p.last_name,
                   pgs.team_id = g.home_team_id as is_home
            FROM player_game_stats pgs
            JOIN players p ON p.id = pgs.player_id
            JOIN games g ON g.id = pgs.game_id
            WHERE pgs.game_id = %s AND pgs.bat_game_played = 1
            ORDER BY is_home DESC, pgs.team_id, p.last_name
        """,
            (game_id,),
        ).fetchall()
        ctx["batting_lines"] = [dict(r) for r in batting]

        pitching = db.execute(
            """
            SELECT pgs.*, p.first_name, p.last_name,
                   pgs.team_id = g.home_team_id as is_home
            FROM player_game_stats pgs
            JOIN players p ON p.id = pgs.player_id
            JOIN games g ON g.id = pgs.game_id
            WHERE pgs.game_id = %s AND pgs.pitch_game_played = 1
            ORDER BY is_home DESC, pgs.team_id, pgs.pitch_game_started DESC
        """,
            (game_id,),
        ).fetchall()
        ctx["pitching_lines"] = [dict(r) for r in pitching]

    return tab_response(request, htmx, "dashboard/partials/game_detail.html", ctx)


# ── Player panel ──────────────────────────────────────────────────────────────


def _load_player_career(player_id: str, db) -> dict | None:
    """Load career data for the career page: season stats, current ratings, injury log."""
    player = db.execute("SELECT * FROM players WHERE id = %s", (player_id,)).fetchone()
    if not player:
        return None

    skills_row = db.execute(
        "SELECT * FROM player_skills WHERE player_id = %s", (player_id,)
    ).fetchone()
    skills = dict(skills_row) if skills_row else {}

    status_row = db.execute(
        "SELECT status FROM player_status WHERE player_id = %s", (player_id,)
    ).fetchone()
    status = status_row["status"] if status_row else "unassigned"
    grades = player_row_to_grades(dict(player), skills, status)

    _skill_labels = {
        "contact": "CON",
        "power": "POW",
        "eye": "EYE",
        "speed": "SPD",
        "base_running": "BSR",
        "bunting": "BUN",
        "clutch": "CLU",
        "catching": "CAT",
        "infield": "INF",
        "outfield": "OF",
        "arm": "ARM",
        "strikes": "STF",
        "accuracy": "CTL",
        "stamina": "STA",
        "recovery": "REC",
        "ground_balls": "GRB",
        "durability": "DUR",
    }
    current_ratings = []
    for key, abbr in _skill_labels.items():
        val = skills.get(key)
        if val is not None:
            current_ratings.append({"abbr": abbr, "grade": skill_to_grade(val)})

    # Season stats — regular season only, ordered newest first
    stat_rows = db.execute(
        """
        SELECT pss.*, s.year, s.name as season_name, t.city as team_city, t.mascot as team_mascot
        FROM player_season_stats pss
        JOIN seasons s ON s.id = pss.season_id
        JOIN teams t ON t.id = pss.team_id
        WHERE pss.player_id = %s AND pss.is_postseason = FALSE
        ORDER BY s.year DESC
        """,
        (player_id,),
    ).fetchall()

    is_pitcher = grades.player_type == "pitcher"
    season_stats = []
    totals: dict = {}
    for r in stat_rows:
        r = dict(r)
        if is_pitcher:
            ip = r["pitch_outs"] / 3.0
            er = r["pitch_earned_runs"]
            era = (er / ip * 9) if ip > 0 else 0.0
            hits = r["pitch_hits"]
            bb = r["pitch_walks"]
            whip = ((hits + bb) / ip) if ip > 0 else 0.0
            row = {
                "year": r["year"],
                "season_name": r["season_name"],
                "team": f"{r['team_city']} {r['team_mascot']}",
                "G": r["pitch_games_played"],
                "GS": r["pitch_games_started"],
                "W": r["pitch_wins"],
                "L": r["pitch_losses"],
                "SV": r["pitch_saves"],
                "IP": round(ip, 1),
                "H": hits,
                "ER": er,
                "BB": bb,
                "K": r["pitch_strike_outs"],
                "HR": r["pitch_home_runs"],
                "ERA": round(era, 2),
                "WHIP": round(whip, 2),
            }
            for k in ("G", "GS", "W", "L", "SV", "H", "ER", "BB", "K", "HR"):
                totals[k] = totals.get(k, 0) + row[k]
            totals["_outs"] = totals.get("_outs", 0) + r["pitch_outs"]
        else:
            ab = r["bat_ab"]
            h = r["bat_hits"]
            bb = r["bat_walks"]
            hbp = r["bat_hbp"]
            sf = r["bat_sac_flys"]
            pa = ab + bb + hbp + sf + r["bat_sac_bunts"]
            obp_denom = ab + bb + hbp + sf
            avg = (h / ab) if ab > 0 else 0.0
            slg_num = (
                h + r["bat_doubles"] + 2 * r["bat_triples"] + 3 * r["bat_home_runs"]
            )
            slg = (slg_num / ab) if ab > 0 else 0.0
            obp = ((h + bb + hbp) / obp_denom) if obp_denom > 0 else 0.0
            row = {
                "year": r["year"],
                "season_name": r["season_name"],
                "team": f"{r['team_city']} {r['team_mascot']}",
                "G": r["bat_games_played"],
                "AB": ab,
                "H": h,
                "2B": r["bat_doubles"],
                "3B": r["bat_triples"],
                "HR": r["bat_home_runs"],
                "RBI": r["bat_rbi"],
                "R": r["bat_runs"],
                "BB": bb,
                "K": r["bat_strike_outs"],
                "SB": r["bat_stolen_bases"],
                "AVG": round(avg, 3),
                "OBP": round(obp, 3),
                "SLG": round(slg, 3),
                "OPS": round(obp + slg, 3),
            }
            for k in ("G", "AB", "H", "2B", "3B", "HR", "RBI", "R", "BB", "K", "SB"):
                totals[k] = totals.get(k, 0) + row[k]
            totals["_ab"] = totals.get("_ab", 0) + ab
            totals["_h"] = totals.get("_h", 0) + h
            totals["_bb"] = totals.get("_bb", 0) + bb
            totals["_hbp"] = totals.get("_hbp", 0) + hbp
            totals["_sf"] = totals.get("_sf", 0) + sf
            totals["_slg_num"] = totals.get("_slg_num", 0) + slg_num
        season_stats.append(row)

    # Compute totals row
    totals_row: dict | None = None
    if totals:
        if is_pitcher:
            tot_outs = totals.pop("_outs", 0)
            tot_ip = tot_outs / 3.0
            tot_er = totals.get("ER", 0)
            tot_h = totals.get("H", 0)
            tot_bb = totals.get("BB", 0)
            tot_era = (tot_er / tot_ip * 9) if tot_ip > 0 else 0.0
            tot_whip = ((tot_h + tot_bb) / tot_ip) if tot_ip > 0 else 0.0
            totals_row = {
                **totals,
                "IP": round(tot_ip, 1),
                "ERA": round(tot_era, 2),
                "WHIP": round(tot_whip, 2),
            }
        else:
            tot_ab = totals.pop("_ab", 0)
            tot_h = totals.pop("_h", 0)
            tot_bb = totals.pop("_bb", 0)
            tot_hbp = totals.pop("_hbp", 0)
            tot_sf = totals.pop("_sf", 0)
            tot_slg_num = totals.pop("_slg_num", 0)
            obp_d = tot_ab + tot_bb + tot_hbp + tot_sf
            tot_avg = (tot_h / tot_ab) if tot_ab > 0 else 0.0
            tot_slg = (tot_slg_num / tot_ab) if tot_ab > 0 else 0.0
            tot_obp = ((tot_h + tot_bb + tot_hbp) / obp_d) if obp_d > 0 else 0.0
            totals_row = {
                **totals,
                "AVG": round(tot_avg, 3),
                "OBP": round(tot_obp, 3),
                "SLG": round(tot_slg, 3),
                "OPS": round(tot_obp + tot_slg, 3),
            }

    # Injuries grouped by season year
    inj_rows = db.execute(
        """
        SELECT pil.injury_date, pil.severity, pil.games_missed, pil.activity,
               s.year as season_year
        FROM player_injury_log pil
        LEFT JOIN seasons s ON s.id = pil.season_id
        WHERE pil.player_id = %s
        ORDER BY pil.injury_date DESC
        """,
        (player_id,),
    ).fetchall()
    injuries_by_year: dict[str, list] = {}
    for r in inj_rows:
        yr = str(r["season_year"]) if r["season_year"] else "Pre-season"
        injuries_by_year.setdefault(yr, []).append(dict(r))

    return {
        "player_id": player_id,
        "first_name": player["first_name"],
        "last_name": player["last_name"],
        "position": player["position"],
        "bats": player["bats"],
        "throws": player["throws"],
        "age": player["age"],
        "overall_grade": grades.overall,
        "player_type": grades.player_type,
        "is_pitcher": is_pitcher,
        "current_ratings": current_ratings,
        "season_stats": season_stats,
        "totals_row": totals_row,
        "injuries_by_year": injuries_by_year,
    }


@router.get(
    "/leagues/{league_id}/players/{player_id}/career", response_class=HTMLResponse
)
async def player_career(
    request: Request, league_id: str, player_id: str, db: DB, compare: str | None = None
):
    gm, redir = _require_league_gm(request, league_id, db)
    if redir:
        return redir
    ctx = {
        "request": request,
        "league_id": league_id,
        "gm_id": gm["id"],
        "player": _load_player_career(player_id, db),
        "compare_player": _load_player_career(compare, db) if compare else None,
    }
    return render("dashboard/partials/player_career.html", ctx)


@router.get(
    "/leagues/{league_id}/players/{player_id}/panel", response_class=HTMLResponse
)
async def player_panel(
    request: Request, league_id: str, player_id: str, db: DB, compare: str | None = None
):
    gm, redir = _require_league_gm(request, league_id, db)
    if redir:
        return redir

    ctx = {
        "request": request,
        "league_id": league_id,
        "gm_id": gm["id"],
        "player": _load_player_detail(player_id, gm, db),
        "compare_player": _load_player_detail(compare, gm, db) if compare else None,
    }
    return render("dashboard/partials/player_panel.html", ctx)


# ── Leaders ───────────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/leaders", response_class=HTMLResponse)
async def leaders_tab(
    request: Request, htmx: IsHTMX, league_id: str, db: DB, category: str = "batting"
):
    gm, redir = _require_league_gm(request, league_id, db)
    if redir:
        return redir
    ctx = _shell_ctx(request, db, gm, league_id, "leaders")
    ctx["category"] = category
    ctx["rows"] = _load_leaders(league_id, category, db)
    return tab_response(request, htmx, "dashboard/partials/leaders.html", ctx)


# ── History ───────────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/history/", response_class=HTMLResponse)
async def history_index(request: Request, league_id: str, db: DB):
    token, name, redir = _require_identity(request)
    if redir:
        return redir
    gm = db.execute(
        "SELECT * FROM gms WHERE user_session = %s LIMIT 1", (token,)
    ).fetchone()
    seasons = db.execute(
        """
        SELECT s.id, s.year, s.name FROM league_seasons ls
        JOIN seasons s ON s.id = ls.season_id
        WHERE ls.league_id = %s ORDER BY s.year DESC
    """,
        (league_id,),
    ).fetchall()
    return render(
        "history/index.html",
        {
            "request": request,
            "league_id": league_id,
            "gm": gm,
            "seasons": [dict(r) for r in seasons],
        },
    )


@router.get("/leagues/{league_id}/history/{year}/", response_class=HTMLResponse)
async def history_season(request: Request, league_id: str, year: int, db: DB):
    gm, redir = _require_league_gm(request, league_id, db)
    if redir:
        return redir

    season = db.execute(
        """
        SELECT s.* FROM league_seasons ls
        JOIN seasons s ON s.id = ls.season_id
        WHERE ls.league_id = %s AND s.year = %s
    """,
        (league_id, year),
    ).fetchone()

    standings = _load_standings(
        league_id, db, season_id=season["id"] if season else None
    )
    evaluation = db.execute(
        """
        SELECT * FROM gm_season_evaluations
        WHERE gm_id = %s AND season_id = %s
    """,
        (gm["id"], season["id"] if season else ""),
    ).fetchone()

    return render(
        "history/season.html",
        {
            "request": request,
            "league_id": league_id,
            "gm": gm,
            "year": year,
            "season": dict(season) if season else None,
            "standings": standings,
            "evaluation": dict(evaluation) if evaluation else None,
        },
    )


# ── DB query helpers ──────────────────────────────────────────────────────────


def _current_season_id(league_id: str, db) -> str | None:
    return SeasonRepository(db).get_current_id_for_league(league_id)


def _current_season_name(league_id: str, db) -> str | None:
    row = db.execute(
        """
        SELECT s.name, s.year FROM league_seasons ls
        JOIN seasons s ON s.id = ls.season_id
        WHERE ls.league_id = %s ORDER BY ls.rowid DESC LIMIT 1
    """,
        (league_id,),
    ).fetchone()
    return f"Season {row['year']}" if row else None


def _current_year(league_id: str, db) -> int:
    row = db.execute(
        """
        SELECT s.year FROM league_seasons ls
        JOIN seasons s ON s.id = ls.season_id
        WHERE ls.league_id = %s ORDER BY ls.rowid DESC LIMIT 1
    """,
        (league_id,),
    ).fetchone()
    return row["year"] if row else 1


def _load_standings(league_id: str, db, season_id: str | None = None) -> list[dict]:
    if not season_id:
        season_id = _current_season_id(league_id, db)
    if not season_id:
        return []

    sr = StandingsRepository(db)
    rows = sr.get_records(league_id, season_id)
    ra_map = sr.get_runs_allowed(season_id)

    human_team_ids = {
        r["team_id"]
        for r in db.execute(
            "SELECT team_id FROM gms WHERE league_id = %s AND NOT is_ai AND team_id IS NOT NULL",
            (league_id,),
        ).fetchall()
    }

    result = []
    for r in rows:
        runs_allowed = ra_map.get(r["team_id"], 0)
        r["runs_allowed"] = runs_allowed
        r["run_diff"] = r["runs_scored"] - runs_allowed
        r["is_human"] = r["team_id"] in human_team_ids
        r["streak"] = 0  # TODO: compute from recent games
        r["last_10"] = None  # TODO
        result.append(r)
    return result


def _load_roster(gm: dict, db) -> list[dict]:
    if not gm["team_id"]:
        return []

    season_id = SeasonRepository(db).get_current_id_for_league(gm["league_id"])
    if not season_id:
        return []

    rows = db.execute(
        """
        SELECT p.id, p.first_name, p.last_name, p.bats, p.throws, p.position,
               ps.status
        FROM league_season_teams lst
        JOIN team_players tp ON tp.team_id = lst.team_id
        JOIN players p ON p.id = tp.player_id
        LEFT JOIN player_status ps ON ps.player_id = p.id
        WHERE lst.team_id = %s AND lst.season_id = %s
        ORDER BY CASE ps.status WHEN '26man' THEN 1 WHEN '40man' THEN 2 ELSE 3 END,
                 p.last_name
    """,
        (gm["team_id"], season_id),
    ).fetchall()

    result = []
    for row in rows:
        skills_row = db.execute(
            "SELECT * FROM player_skills WHERE player_id = %s", (row["id"],)
        ).fetchone()
        skills = dict(skills_row) if skills_row else {}
        grades = player_row_to_grades(dict(row), skills, row["status"] or "unassigned")
        result.append(grades.model_dump())
    return result


def _load_draft_board(draft_id: str, db) -> list[dict]:
    picked = {
        r["player_id"]
        for r in db.execute(
            "SELECT player_id FROM draft_picks WHERE draft_id = %s", (draft_id,)
        ).fetchall()
    }

    players = db.execute(
        """
        SELECT p.*, ps.status FROM players p
        JOIN player_status ps ON ps.player_id = p.id
        JOIN drafts d ON d.id = %s
        WHERE ps.status IN ('free_agent', 'unassigned', 'prospect')
        AND p.league_id = d.league_id
    """,
        (draft_id,),
    ).fetchall()

    board = []
    for row in players:
        if row["id"] in picked:
            continue
        skills_row = db.execute(
            "SELECT * FROM player_skills WHERE player_id = %s", (row["id"],)
        ).fetchone()
        skills = dict(skills_row) if skills_row else {}
        grades = player_row_to_grades(dict(row), skills, row["status"])
        board.append(grades.model_dump())
    return board


def _load_leaders(league_id: str, category: str, db) -> list[dict]:
    season_id = _current_season_id(league_id, db)
    if not season_id:
        return []

    if category == "batting":
        rows = db.execute(
            """
            SELECT p.first_name, p.last_name, t.city || ' ' || t.mascot as team,
                   SUM(pgs.bat_ab) as AB, SUM(pgs.bat_hits) as H,
                   SUM(pgs.bat_home_runs) as HR, SUM(pgs.bat_rbi) as RBI,
                   SUM(pgs.bat_walks) as BB, SUM(pgs.bat_strike_outs) as K,
                   SUM(pgs.bat_stolen_bases) as SB,
                   ROUND(CAST(SUM(pgs.bat_hits) AS FLOAT) / NULLIF(SUM(pgs.bat_ab), 0), 3) as AVG
            FROM player_game_stats pgs
            JOIN games g ON g.id = pgs.game_id
            JOIN players p ON p.id = pgs.player_id
            JOIN team_game_stats tgs ON tgs.game_id = pgs.game_id AND tgs.team_id = pgs.team_id
            JOIN teams t ON t.id = pgs.team_id
            WHERE g.season_id = %s AND pgs.bat_game_played = 1
            GROUP BY pgs.player_id
            HAVING SUM(pgs.bat_ab) >= 10
            ORDER BY AVG DESC LIMIT 50
        """,
            (season_id,),
        ).fetchall()
    else:  # pitching
        rows = db.execute(
            """
            SELECT p.first_name, p.last_name, t.city || ' ' || t.mascot as team,
                   SUM(pgs.pitch_win) as W, SUM(pgs.pitch_loss) as L,
                   SUM(pgs.pitch_save) as SV,
                   ROUND(SUM(pgs.pitch_outs) / 3.0, 1) as IP,
                   SUM(pgs.pitch_strike_outs) as K,
                   SUM(pgs.pitch_walks) as BB,
                   ROUND(CAST(SUM(pgs.pitch_earned_runs) AS FLOAT) /
                         NULLIF(SUM(pgs.pitch_outs) / 3.0, 0) * 9, 2) as ERA
            FROM player_game_stats pgs
            JOIN games g ON g.id = pgs.game_id
            JOIN players p ON p.id = pgs.player_id
            JOIN teams t ON t.id = pgs.team_id
            WHERE g.season_id = %s AND pgs.pitch_game_played = 1
            GROUP BY pgs.player_id
            HAVING SUM(pgs.pitch_outs) >= 9
            ORDER BY ERA ASC LIMIT 50
        """,
            (season_id,),
        ).fetchall()

    return [dict(r) for r in rows]


def _load_player_detail(player_id: str | None, gm: dict, db) -> dict | None:
    if not player_id:
        return None

    player = db.execute("SELECT * FROM players WHERE id = %s", (player_id,)).fetchone()
    if not player:
        return None

    skills_row = db.execute(
        "SELECT * FROM player_skills WHERE player_id = %s", (player_id,)
    ).fetchone()
    skills = dict(skills_row) if skills_row else {}

    status_row = db.execute(
        "SELECT status FROM player_status WHERE player_id = %s", (player_id,)
    ).fetchone()
    status = status_row["status"] if status_row else "unassigned"

    grades = player_row_to_grades(dict(player), skills, status)

    # Team info
    team_row = db.execute(
        """
        SELECT t.city, t.mascot FROM team_players tp
        JOIN teams t ON t.id = tp.team_id
        WHERE tp.player_id = %s LIMIT 1
    """,
        (player_id,),
    ).fetchone()

    # Energy
    energy = None
    if grades.player_type == "pitcher":
        ps = db.execute(
            "SELECT * FROM pitcher_state WHERE player_id = %s", (player_id,)
        ).fetchone()
        if ps:
            energy = {
                "energy_pct": round(ps["current_energy"] * 100),
                "energy_max_pct": round(ps["max_energy"] * 100),
                "consecutive_days": ps["consecutive_days"],
                "last_game_date": ps["last_game_date"],
                "last_pitch_count": ps["last_pitch_count"],
            }
    else:
        pe = db.execute(
            "SELECT * FROM player_energy WHERE player_id = %s", (player_id,)
        ).fetchone()
        if pe:
            energy = {
                "energy_pct": round(pe["current_energy"] * 100),
                "energy_max_pct": round(pe["max_energy"] * 100),
                "consecutive_days": pe["consecutive_days"],
                "last_game_date": pe["last_game_date"],
                "season_games_played": pe["season_games_played"],
            }

    # Injury
    inj = db.execute(
        "SELECT * FROM player_injuries WHERE player_id = %s", (player_id,)
    ).fetchone()
    inj_log = db.execute(
        """
        SELECT injury_date, severity, games_missed FROM player_injury_log
        WHERE player_id = %s ORDER BY injury_date DESC LIMIT 5
    """,
        (player_id,),
    ).fetchall()

    # Build grades dict matching template expectations
    all_grades = {}
    _skill_labels = {
        "contact": "Contact",
        "power": "Power",
        "eye": "Eye",
        "speed": "Speed",
        "base_running": "Baserunning",
        "bunting": "Bunting",
        "clutch": "Clutch",
        "catching": "Catching",
        "infield": "Infield",
        "outfield": "Outfield",
        "arm": "Arm",
        "strikes": "Stuff",
        "accuracy": "Control",
        "stamina": "Stamina",
        "recovery": "Recovery",
        "ground_balls": "Ground Balls",
        "durability": "Durability",
    }
    for key, label in _skill_labels.items():
        val = skills.get(key)
        all_grades[key] = {
            "label": label,
            "grade": skill_to_grade(val) if val is not None else "%s",
        }

    d = grades.model_dump()
    d.update(
        {
            "player_id": player_id,
            "team_city": team_row["city"] if team_row else "",
            "team_mascot": team_row["mascot"] if team_row else "",
            "overall_grade": grades.overall,
            "grades": all_grades,
            "injured": bool(inj and inj["games_remaining"] > 0),
            "games_remaining": inj["games_remaining"] if inj else 0,
            "injury_log": [dict(r) for r in inj_log],
            "stats": None,  # TODO: season stats (same logic as gms.py get_player_detail)
        }
    )
    if energy:
        d.update(energy)
    return d
