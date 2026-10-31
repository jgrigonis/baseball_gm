# src/web/utils.py
import hashlib
from functools import lru_cache
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.api.services import all_star, trades
from src.api.services.coach import coach_ctx, mark_visit
from src.api.services.ready_check import is_multiplayer
from src.api.view_models.league_info import league_info
from src.db.repositories.all_star_repo import AllStarRepository
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.league.league_modes import injuries_allowed
from src.league.trade_deadline import trades_enabled_for
from src.team.colors import team_badge

# Templates are in src/web/templates/ relative to the project root
_TEMPLATES_DIR = Path(__file__).parent / "templates"

# The single Jinja2 environment for the whole app: routers render through
# templates.TemplateResponse and tab partials render through render().
templates = Jinja2Templates(directory=_TEMPLATES_DIR)
templates.env.globals["team_badge"] = team_badge

_STATIC_DIR = Path(__file__).parent / "static"


@lru_cache(maxsize=64)
def _static_hash(path: str, mtime_ns: int) -> str:
    return hashlib.sha1((_STATIC_DIR / path).read_bytes()).hexdigest()[:10]


def static_url(path: str) -> str:
    """URL for a file under static/, stamped with a hash of its contents, so
    a deploy that changes the file makes browsers fetch it again instead of
    using a cached copy."""
    try:
        mtime_ns = (_STATIC_DIR / path).stat().st_mtime_ns
    except FileNotFoundError:
        return f"/static/{path}"
    return f"/static/{path}?v={_static_hash(path, mtime_ns)}"


templates.env.globals["static_url"] = static_url


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

    if state not in ("season", "playoffs", "preseason", "offseason", "complete"):
        if "schedule" in post:
            post.remove("schedule")

    if state in ("playoffs", "offseason", "complete"):
        post.append("playoffs")

    post.append("draft")  # Results tab
    return post


# The tabs a viewer of a public league sees: the ones that read the same
# whoever is looking. Schedule, roster, lineup and strategy are one GM's own.
_VIEWER_TABS = ("standings", "leaders", "stats", "playoffs", "allstar")


def _viewer_tabs(tabs: list[str], draft_complete: bool) -> list[str]:
    """Only the draft's results are open to viewers, not the board in progress."""
    return [t for t in tabs if t in _VIEWER_TABS or (t == "draft" and draft_complete)]


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


def _current_league_date(
    db, season_id: str | None, state: str, all_star_game: bool = True
) -> str | None:
    """Return the next unplayed game date, or last played date if season is
    over. With all_star_game, the All-Star Game's date while it's the next
    thing to play."""
    if not season_id:
        return None
    if state not in (
        "draft",
        "preseason",
        "season",
        "playoffs",
        "offseason",
        "complete",
    ):
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
        # The All-Star Game is played before the first games after the break.
        asg = all_star_game and all_star.game_day(db, season_id, row["game_date"])
        return asg or row["game_date"]
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
        "is_viewer": bool(gm.get("is_viewer")),
        # Admins see ids and the numbers behind letter grades.
        "is_admin": bool(user and user.get("is_admin")),
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
                    "is_commissioner": gm.get("id") is not None
                    and league["commissioner_gm_id"] == gm["id"],
                    "draft_complete": draft_complete,
                    # Several human GMs: the league advances by ready-check,
                    # so the Sim buttons give way to the ready bar.
                    "multiplayer": is_multiplayer(db, league_id),
                    # A league without injuries has no Until Injury button.
                    "injuries_enabled": injuries_allowed(league),
                }
            )
            tabs = _compute_visible_tabs(league["state"], draft_complete)
            # Leagues that trade get a Trades tab once the draft is done, next
            # to the roster. It stays for the trade history once trades close.
            if (
                draft_complete
                and "roster" in tabs
                and trades_enabled_for(league["mode"])
            ):
                tabs.insert(tabs.index("roster") + 1, "trades")
                if not ctx["is_viewer"]:
                    # Offers and votes waiting on this GM: the tab's badge.
                    ctx["trade_inbox"] = trades.inbox_count(db, league_id, gm)
            if ctx["is_viewer"]:
                tabs = _viewer_tabs(tabs, draft_complete)
            # Now we have the state, so calculate visibility automatically
            ctx["visible_tabs"] = tabs
            # The top bar's season pill opens the league's settings.
            if league["state"] != "lobby":
                ctx["league_info"] = league_info(db, league)
            if not ctx["is_viewer"]:
                mark_visit(db, league, active_tab)
                ctx["coach"] = coach_ctx(db, league)

    # 3. Fetch Team Data if team_id exists
    if ctx["team_id"]:
        team_repo = TeamRepository(db)
        team = team_repo.get_city_and_mascot(ctx["team_id"])
        if team:
            ctx["team_name"] = f"{team['city']} {team['mascot']}"
            ctx["team_city"] = team["city"]
            ctx["team_mascot"] = team["mascot"]

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
    elif league_state_for_season in ("playoffs", "offseason", "complete"):
        # During playoffs/offseason, and once the league is complete, use the season that has series records.
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
    # The All-Star tab, from the day the ballot opens to the end of the
    # playoffs. The shown season's All-Stars get a star by their name.
    as_phase = (
        all_star.phase(db, ctx["season_id"])
        if ctx["league_state"] in ("season", "playoffs")
        else "none"
    )
    ctx["all_star_phase"] = as_phase
    tabs = ctx.get("visible_tabs")
    if as_phase in ("open", "done", "played") and tabs and "standings" in tabs:
        tabs.insert(tabs.index("standings"), "allstar")
        if as_phase == "open" and not ctx["is_viewer"] and ctx["team_id"]:
            ctx["all_star_ballot_due"] = (
                AllStarRepository(db).ballot(ctx["season_id"], ctx["team_id"]) is None
            )
        # A captain with a pick to make in the All-Star draft.
        if as_phase == "done" and not ctx["is_viewer"]:
            ctx["all_star_pick_due"] = all_star.my_turn(
                db, league_id, ctx["season_id"], ctx["team_id"]
            )
    ctx["all_star_ids"] = (
        AllStarRepository(db).ids(ctx["season_id"]) if ctx["season_id"] else set()
    )
    # Rookies get an (R) by their name. Status goes by the newest season, so a
    # player drafted this offseason shows as a rookie straight away.
    newest = sr.get_newest_for_league(league_id) if league_id else None
    ctx["rookie_ids"] = (
        PlayerSeasonStatsRepository(db).get_rookie_ids(league_id, newest["id"])
        if newest
        else set()
    )
    db.commit()
    return ctx
