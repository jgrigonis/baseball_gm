# src/web/utils.py
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.api.services.ready_check import is_multiplayer
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository

# Templates are in src/web/templates/ relative to the project root
_TEMPLATES_DIR = Path(__file__).parent / "templates"

# The single Jinja2 environment for the whole app: routers render through
# templates.TemplateResponse and tab partials render through render().
templates = Jinja2Templates(directory=_TEMPLATES_DIR)


def render(name: str, context: dict) -> HTMLResponse:
    template = templates.get_template(name)
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
    if state not in ("draft", "preseason", "season", "playoffs", "offseason"):
        return None
    if state in ("draft", "offseason"):
        sr = SeasonRepository(db)
        row = sr.get_year(season_id)
        if row:
            year = row["year"]
            if state == "draft":
                if sr.has_a_completed_game(season_id):
                    year += 1
            return f"{year}-03-22"
        else:
            return None
    # Next unplayed regular season game
    game_repo = GameRepository(db)
    row = game_repo.get_next_unplayed_date(season_id)
    if row:
        return row["game_date"]
    row = game_repo.last_game_date(season_id)
    return row["d"] if row else None


def _games_remaining(db, season_id: str | None) -> int:
    if not season_id:
        return 0
    game_repo = GameRepository(db)
    num = game_repo.games_remaining(season_id)
    # TODO test that this change to a simpler query didn't break something
    # row = db.execute(
    #     """SELECT COUNT(*) FROM games g
    #        WHERE g.season_id = %s AND g.completed = 0
    #          AND (
    #              g.series_id IS NULL
    #              OR NOT EXISTS (
    #                  SELECT 1 FROM games sg
    #                  JOIN series sr ON sr.id = sg.series_id
    #                  WHERE sg.series_id = g.series_id AND sg.completed = 1
    #                  GROUP BY sg.winner_id
    #                  HAVING COUNT(*) >= MAX(
    #                      CASE WHEN sr.name IN ('1v8','2v7','3v6','4v5') THEN 3 ELSE 4 END
    #                  )
    #              )
    #          )""",
    #     (season_id,),
    # ).fetchone()
    # return row["count"] if row else 0
    return num if num else 0


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
        lr = LeagueRepository(db)
        league = lr.get_by_id(league_id)
        draft_complete = lr.draft_complete(league_id)
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
                    # Several human GMs: the league advances by ready-check,
                    # so the Sim buttons give way to the ready bar.
                    "multiplayer": is_multiplayer(db, league_id),
                }
            )
            tabs = _compute_visible_tabs(league["state"], draft_complete)
            # Now we have the state, so calculate visibility automatically
            ctx["visible_tabs"] = tabs

    # 3. Fetch Team Data if team_id exists
    if ctx["team_id"]:
        team_repo = TeamRepository(db)
        team = team_repo.get_city_mascot(ctx["team_id"])
        if team:
            ctx["team_name"] = team

    # 4. Season/Date logic
    league_state_for_season = league["state"] if league else "lobby"

    sr = SeasonRepository(db)
    if league_state_for_season == "draft":
        # During draft, show the last COMPLETED season for standings/schedule/etc.
        # Year 2 is being drafted but has no games — year 1's data is what's useful.
        # Fallback to newest if nothing completed yet (first ever draft).
        season = sr.get_last_with_completed_games(
            league_id
        ) or sr.get_newest_for_league(league_id)
    elif league_state_for_season in ("playoffs", "offseason"):
        # During playoffs/offseason, use the season that has series records.
        # Fallback to newest if no series yet.
        season = sr.get_last_with_series_row(league_id) or sr.get_newest_for_league(
            league_id
        )
    else:
        # season/preseason: show the newest season (current active season)
        season = sr.get_newest_for_league(league_id)
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
