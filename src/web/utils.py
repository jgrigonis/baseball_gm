# src/web/utils.py
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from jinja2 import Environment, FileSystemLoader

# Templates are in src/web/templates/ relative to the project root
_TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory="src/web/templates")

_jinja_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=True,
)


def render(name: str, context: dict) -> HTMLResponse:
    template = _jinja_env.get_template(name)
    return HTMLResponse(template.render(**context))


def _compute_visible_tabs(state: str, draft_complete: bool = False) -> list[str]:
    if state == "lobby":
        return []

    # If draft isn't done, show the draft tab prominently
    if not draft_complete:
        return [
            "draft",
            "roster",
            "lineup",
            "standings",
            "leaders",
            "stats",
            "strategy",
        ]

    # Standard season tabs
    post = ["roster", "lineup", "schedule", "standings", "leaders", "stats", "strategy"]

    if state not in ("season", "playoffs", "preseason", "offseason"):
        if "schedule" in post:
            post.remove("schedule")

    if state in ("playoffs", "offseason"):
        post.append("playoffs")

    post.append("draft")  # Results tab
    return post


# def tab_visible(state: str | None) -> list[str]:
#     """Determines which tabs to show based on league state."""
#     if not state or state == "lobby":
#         return []
#     always = ["standings", "leaders", "roster", "lineup", "strategy"]
#     if state == "draft":
#         return ["draft"] + always
#     if state in ("season", "playoffs"):
#         return always + ["schedule"]
#     return always


def tab_response(request: Request, htmx: bool, template_name: str, ctx: dict):
    """The main entry point for your route responses."""
    # Ensure tab visibility is always calculated here so you don't
    # have to manually call it in every single route.
    if "tab_visible" not in ctx:
        ctx["tab_visible"] = _compute_visible_tabs(ctx.get("league_state"))
    if htmx:
        return render(template_name, ctx)
    ctx["tab_template"] = template_name
    return render("dashboard/shell.html", ctx)


def _current_league_date(db, season_id: str | None, state: str) -> str | None:
    """Return the next unplayed game date, or last played date if season is over."""
    if not season_id:
        return None
    if state not in ("draft", "preseason", "season", "playoffs"):
        return None
    if state == "draft":
        # print(season_id)
        row = db.execute(
            "SELECT year FROM seasons WHERE id = %s",
            (season_id,),
        ).fetchone()
        if row:
            year = row["year"] 
            # print(f"{year}-04-01")
            return f"{year}-04-01"
        else:
            return None
    
    # Next unplayed regular season game
    row = db.execute(
        "SELECT game_date FROM games WHERE season_id = %s AND completed = 0 AND series_id IS NULL ORDER BY game_date ASC LIMIT 1",
        (season_id,),
    ).fetchone()
    if row:
        return row["game_date"]
    # Playoffs: next unplayed playoff game
    row = db.execute(
        "SELECT game_date FROM games WHERE season_id = %s AND completed = 0 ORDER BY game_date ASC LIMIT 1",
        (season_id,),
    ).fetchone()
    if row:
        return row["game_date"]
    # All done — last played date
    row = db.execute(
        "SELECT MAX(game_date) as d FROM games WHERE season_id = %s AND completed = 1",
        (season_id,),
    ).fetchone()
    return row["d"] if row else None


def _games_remaining(db, season_id: str | None) -> int:
    if not season_id:
        return 0
    row = db.execute(
        "SELECT COUNT(*) FROM games WHERE season_id = %s AND completed = 0",
        (season_id,),
    ).fetchone()
    return row["count"] if row else 0


def _draft_is_complete(db, league_id: str) -> bool:
    row = db.execute(
        """SELECT d.state FROM drafts d
           JOIN league_seasons ls ON ls.season_id = d.season_id
           JOIN seasons s ON s.id = ls.season_id
           WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
        (league_id,),
    ).fetchone()
    return bool(row and row["state"] == "complete")


def _shell_ctx(
    request: Request,
    db,
    gm: dict | None,
    league_id: str | None = None,
    active_tab: str | None = None,
    user: dict | None = None,  # Keep as optional for the 'web' version needs
) -> dict:
    league = None  # prevent any possible NameError
    # 1. Start with the core info we definitely have
    ctx = {
        "request": request,
        "active_tab": active_tab,
        "gm_id": gm.get("id"),
        "gm_display_name": (
            gm.get("display_name")
            if gm
            else (user.get("display_name") if user else "Guest")
        ),
        # "gm_display_name": gm.get("display_name"),
        "league_id": league_id,
        "team_id": gm.get("team_id"),
        "league_state": "lobby",  # Default
        "reentry_enabled": True,
        "season_id": None,
        "season_name": None,
        "current_date": None,
    }

    # 2. Fetch League Data if league_id exists
    if league_id:
        league = db.execute(
            "SELECT * FROM leagues WHERE id = %s", (league_id,)
        ).fetchone()
        draft_complete = _draft_is_complete(db, league_id)
        if league:
            ctx.update(
                {
                    "league_name": league["name"],
                    "league_state": league["state"],
                    "league_mode": league["mode"],
                    "join_code": league["join_code"],
                    "num_teams": league["num_teams"],
                    "decision_window_sec": league["decision_window_sec"],
                    "draft_window_sec": league["draft_window_sec"],
                    "reentry_enabled": bool(league["reentry_enabled"]),
                    "pace_control": league["pace_control"],
                    "is_commissioner": league["commissioner_gm_id"] == gm.get("id"),
                    "draft_complete": draft_complete,
                }
            )
            tabs = _compute_visible_tabs(league["state"], draft_complete)
            # Now we have the state, so calculate visibility automatically
            ctx["visible_tabs"] = tabs

    # 3. Fetch Team Data if team_id exists
    if ctx["team_id"]:
        team = db.execute(
            "SELECT city, mascot FROM teams WHERE id = %s", (ctx["team_id"],)
        ).fetchone()
        if team:
            ctx["team_name"] = f"{team['city']} {team['mascot']}"

    # 4. Season/Date logic
    league_state_for_season = league["state"] if league else "lobby"

    if league_state_for_season == "draft":
        # During draft, show the last COMPLETED season for standings/schedule/etc.
        # Year 2 is being drafted but has no games — year 1's data is what's useful.
        season = db.execute(
            """SELECT s.* FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s
                 AND EXISTS (
                   SELECT 1 FROM games g WHERE g.season_id = s.id AND g.completed = 1
                 )
               ORDER BY s.year DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
        # Fallback to newest if nothing completed yet (first ever draft)
        if season is None:
            season = db.execute(
                """SELECT s.* FROM seasons s
                   JOIN league_seasons ls ON ls.season_id = s.id
                   WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
                (league_id,),
            ).fetchone()
    elif league_state_for_season in ("playoffs", "offseason"):
        # During playoffs/offseason, use the season that has series records
        season = db.execute(
            """SELECT s.* FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s
                 AND EXISTS (
                   SELECT 1 FROM series sr WHERE sr.season_id = s.id
                 )
               ORDER BY s.year DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
        # Fallback to newest if no series yet
        if season is None:
            season = db.execute(
                """SELECT s.* FROM seasons s
                   JOIN league_seasons ls ON ls.season_id = s.id
                   WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
                (league_id,),
            ).fetchone()
    else:
        # season/preseason: show the newest season (current active season)
        season = db.execute(
            """SELECT s.* FROM seasons s
               JOIN league_seasons ls ON ls.season_id = s.id
               WHERE ls.league_id = %s ORDER BY s.year DESC LIMIT 1""",
            (league_id,),
        ).fetchone()
    if season:
        ctx.update(
            {
                "season_id": season["id"],
                "season_name": season["name"],
                "games_remaining": _games_remaining(db, season["id"]),
                "current_date": _current_league_date(
                    db, season["id"], ctx["league_state"]
                ),
            }
        )
    db.commit()
    return ctx
