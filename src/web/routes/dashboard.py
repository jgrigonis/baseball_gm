# src/web/routes/dashboard.py
"""
src/web/routes/dashboard.py

The main game interface. One shell URL per league, content varies by state.
All tab routes return either full pages (direct nav) or partials (HTMX swap).
"""

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(prefix="/leagues/{league_id}")
templates = Jinja2Templates(directory="src/web/templates")


# ── Helpers ───────────────────────────────────────────────────────────────────


def is_htmx(request: Request) -> bool:
    """True if this is an HTMX partial request."""
    return request.headers.get("HX-Request") == "true"


def shell_context(request: Request, league_id: str, active_tab: str | None = None):
    """
    Base context injected into every dashboard template.
    TODO: load real league + gm from DB using session cookie.
    """
    return {
        "request": request,
        "league_id": league_id,
        "league_name": "Dev League",  # TODO
        "league_state": "season",  # TODO: from DB
        "league_mode": "blitz",  # TODO: from DB
        "join_code": "ABC123",  # TODO
        "gm_display_name": "Dev GM",  # TODO
        "team_name": "Portland Lumber",  # TODO
        "team_id": None,  # TODO
        "active_tab": active_tab,
        "is_commissioner": True,  # TODO
    }


def tab_visible(state: str) -> list[str]:
    """Which tabs are shown for a given league state."""
    always = ["standings", "leaders", "roster", "lineup", "strategy"]
    draft_tab = ["draft"]
    sched_tab = ["schedule"]

    if state == "lobby":
        return []
    if state == "draft":
        return draft_tab + always
    if state == "season":
        return always + sched_tab
    if state == "playoffs":
        return always + sched_tab
    return always  # evaluation, offseason


# ── Dashboard shell ───────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, league_id: str):
    ctx = shell_context(request, league_id)
    state = ctx["league_state"]

    if state == "lobby":
        return templates.TemplateResponse("dashboard/lobby.html", ctx)

    if state == "draft":
        return RedirectResponse(f"/leagues/{league_id}/draft")

    if state in ("season", "playoffs"):
        return RedirectResponse(f"/leagues/{league_id}/standings")

    if state == "evaluation":
        # TODO: get current season year
        year = 1
        return RedirectResponse(f"/leagues/{league_id}/history/{year}/")

    return templates.TemplateResponse("dashboard/shell.html", ctx)


# ── Tab routes ────────────────────────────────────────────────────────────────
# Each route checks if it's an HTMX request:
#   - HTMX: return just the content partial (swapped into #tab-content)
#   - Direct: return the full shell with the partial embedded


@router.get("/draft", response_class=HTMLResponse)
async def draft(request: Request, league_id: str):
    ctx = {**shell_context(request, league_id, "draft")}
    # TODO: load draft board data
    ctx["players"] = []
    template = (
        "dashboard/partials/draft.html" if is_htmx(request) else "dashboard/shell.html"
    )
    ctx["tab_template"] = "dashboard/partials/draft.html"
    return templates.TemplateResponse(template, ctx)


@router.get("/standings", response_class=HTMLResponse)
async def standings(request: Request, league_id: str):
    ctx = {**shell_context(request, league_id, "standings")}
    # TODO: load standings from DB
    ctx["divisions"] = []
    template = (
        "dashboard/partials/standings.html"
        if is_htmx(request)
        else "dashboard/shell.html"
    )
    ctx["tab_template"] = "dashboard/partials/standings.html"
    return templates.TemplateResponse(template, ctx)


@router.get("/leaders", response_class=HTMLResponse)
async def leaders(request: Request, league_id: str, category: str = "batting"):
    ctx = {**shell_context(request, league_id, "leaders")}
    # TODO: load leaderboards
    ctx["category"] = category
    ctx["rows"] = []
    template = (
        "dashboard/partials/leaders.html"
        if is_htmx(request)
        else "dashboard/shell.html"
    )
    ctx["tab_template"] = "dashboard/partials/leaders.html"
    return templates.TemplateResponse(template, ctx)


@router.get("/roster", response_class=HTMLResponse)
async def roster(request: Request, league_id: str):
    ctx = {**shell_context(request, league_id, "roster")}
    # TODO: load GM's roster
    ctx["players"] = []
    template = (
        "dashboard/partials/roster.html" if is_htmx(request) else "dashboard/shell.html"
    )
    ctx["tab_template"] = "dashboard/partials/roster.html"
    return templates.TemplateResponse(template, ctx)


@router.get("/lineup", response_class=HTMLResponse)
async def lineup(request: Request, league_id: str):
    ctx = {**shell_context(request, league_id, "lineup")}
    # TODO: load lineup preferences
    ctx["batting_order"] = []
    ctx["rotation"] = []
    ctx["bullpen"] = []
    template = (
        "dashboard/partials/lineup.html" if is_htmx(request) else "dashboard/shell.html"
    )
    ctx["tab_template"] = "dashboard/partials/lineup.html"
    return templates.TemplateResponse(template, ctx)


@router.get("/schedule", response_class=HTMLResponse)
async def schedule(request: Request, league_id: str, date: str | None = None):
    ctx = {**shell_context(request, league_id, "schedule")}
    # TODO: load games for date (default: most recent)
    ctx["game_date"] = date
    ctx["games"] = []
    ctx["prev_date"] = None
    ctx["next_date"] = None
    template = (
        "dashboard/partials/schedule.html"
        if is_htmx(request)
        else "dashboard/shell.html"
    )
    ctx["tab_template"] = "dashboard/partials/schedule.html"
    return templates.TemplateResponse(template, ctx)


@router.get("/schedule/{date}", response_class=HTMLResponse)
async def schedule_date(request: Request, league_id: str, date: str):
    return await schedule(request, league_id, date)


@router.get("/strategy", response_class=HTMLResponse)
async def strategy(request: Request, league_id: str):
    ctx = {**shell_context(request, league_id, "strategy")}
    # TODO: load GM profile from DB, translate string values to 0-based indexes
    ctx["profile"] = {
        "lineup_style_index": 1,
        "steal_aggression_index": 1,
        "sac_bunt_index": 1,
        "platoon_usage_index": 0,
        "starter_usage_index": 1,
        "closer_usage_index": 0,
        "bullpen_pref_index": 0,
    }
    template = (
        "dashboard/partials/strategy.html"
        if is_htmx(request)
        else "dashboard/shell.html"
    )
    ctx["tab_template"] = "dashboard/partials/strategy.html"
    return templates.TemplateResponse(template, ctx)


@router.patch("/strategy")
async def save_strategy(request: Request, league_id: str):
    form = await request.form()
    index_maps = {
        "lineup_style": ["traditional", "analytics", "speed-first", "power-first"],
        "steal_aggression": ["conservative", "standard", "aggressive"],
        "sac_bunt": ["never", "situational", "frequent"],
        "platoon_usage": ["none", "vs-handedness", "aggressive"],
        "starter_usage": ["let-them-work", "pitch-count-strict", "matchup-based"],
        "closer_usage": ["saves-only", "high-leverage", "best-available"],
        "bullpen_pref": ["deep-pen", "starter-heavy"],
    }
    profile = {}
    for field, options in index_maps.items():
        idx = int(form.get(field, 0))
        profile[field] = options[min(idx, len(options) - 1)]
    # TODO: write profile to DB via gm_profiles table
    return HTMLResponse(
        '<span style="color:var(--green);font-family:var(--font-mono);font-size:11px;">✓ Saved</span>'
    )


@router.get("/players/{player_id}/panel", response_class=HTMLResponse)
async def player_panel(
    request: Request, league_id: str, player_id: str, compare: str | None = None
):
    """Slide-in player detail panel. Pass ?compare=<id> for side-by-side."""
    ctx = {**shell_context(request, league_id)}
    # TODO: load player + optional compare player from DB
    ctx["player"] = None
    ctx["compare_player"] = None
    return templates.TemplateResponse("dashboard/partials/player_panel.html", ctx)


@router.get("/games/{game_id}", response_class=HTMLResponse)
async def game_detail(request: Request, league_id: str, game_id: str):
    ctx = {**shell_context(request, league_id, "schedule")}
    # TODO: load box score + play-by-play
    ctx["game"] = None
    ctx["tab_template"] = "dashboard/partials/game_detail.html"
    return templates.TemplateResponse("dashboard/shell.html", ctx)
