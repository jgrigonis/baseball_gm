# src/web/utils.py
import hashlib
from functools import lru_cache
from datetime import date
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from src.config import settings
from src.player.injury_types import injury_effect, injury_label
from src.api.services import (
    all_star,
    firing,
    hall_of_fame,
    next_move,
    owner_office,
    takeover,
    trades,
)
from src.api.schemas import grade_letter
from src.api.services.admin import uses_default_admin_name
from src.api.services.coach import coach_ctx, mark_visit
from src.api.services.ready_check import is_multiplayer
from src.api.view_models.league_info import league_info
from src.db.repositories.all_star_repo import AllStarRepository
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.games_repo import GameRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.happiness_repo import HappinessRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.news_repo import NewsRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.team_repo import TeamRepository
from src.league.league_modes import get_mode, has_money, injuries_allowed
from src.league.trade_deadline import (
    OFFSEASON_STATES,
    deadline_date,
    trades_enabled_for,
)
from src.player.face import player_face
from src.player.positions import display_position
from src.team.colors import team_badge

# Templates are in src/web/templates/ relative to the project root
_TEMPLATES_DIR = Path(__file__).parent / "templates"

# The single Jinja2 environment for the whole app: routers render through
# templates.TemplateResponse and tab partials render through render().
templates = Jinja2Templates(directory=_TEMPLATES_DIR)
templates.env.globals["team_badge"] = team_badge
# An illustrated face from the player's id, team and age (src/player/face.py)
templates.env.globals["player_face"] = player_face
# "P" for any pitcher, so a generated sp/rp lean never shows ("2B" otherwise)
templates.env.filters["pos_label"] = display_position


def long_date(value) -> str:
    """'2028-07-06' (or a date) -> 'July 6, 2028'; anything else as is."""
    try:
        d = value if hasattr(value, "strftime") else date.fromisoformat(str(value)[:10])
    except ValueError:
        return str(value)
    return f"{d.strftime('%B')} {d.day}, {d.year}"


templates.env.filters["long_date"] = long_date


def grade_class(grade: str | None) -> str:
    """CSS class suffix for a letter grade, matching gradeClass() in
    static/js/grades.js: "A+" -> "A-plus", "B-" -> "B-minus". A skill shown
    as a number takes its letter's color."""
    g = grade_letter(grade)
    if g.endswith("+"):
        return g[:-1] + "-plus"
    if g.endswith("-"):
        return g[:-1] + "-minus"
    return g


templates.env.globals["grade_class"] = grade_class


def grade_tier(grade: str | None) -> str:
    """The player panel's elite/good/poor color for a grade or skill number."""
    g = grade_letter(grade)
    if g.startswith("A"):
        return "elite"
    if g.startswith("B") or g == "C+":
        return "good"
    if g.startswith("D") or g == "F":
        return "poor"
    return ""


templates.env.globals["grade_tier"] = grade_tier
# The injury's name, or its severity for injuries from before injury types
templates.env.globals["injury_label"] = injury_label
# What an injury left for good (lasting effects), from its log row
templates.env.globals["injury_effect"] = injury_effect

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
templates.env.globals["discord_url"] = settings.discord_url
templates.env.globals["uses_default_admin_name"] = uses_default_admin_name


def render(name: str, context: dict) -> HTMLResponse:
    template = templates.get_template(name)
    return HTMLResponse(template.render(**context))


def _compute_visible_tabs(state: str, draft_complete: bool = False) -> list[str]:
    if state == "lobby":
        return []

    # Before the draft is done there are fewer tabs. The Draft tab is at the
    # right end either way, so it stays put when it turns into the results.
    if not draft_complete:
        return [
            "roster",
            "lineup",
            "depth",
            "standings",
            "power",
            "leaders",
            "stats",
            "free-agents",
            "owner",
            "budget",
            "strategy",
            "draft",
        ]

    # Standard season tabs
    post = [
        "roster",
        "lineup",
        "depth",
        "schedule",
        "standings",
        "power",
        "headlines",
        "leaders",
        "stats",
        "free-agents",
        "owner",
        "budget",
        "strategy",
    ]

    if state not in ("season", "playoffs", "preseason", "offseason", "complete"):
        if "schedule" in post:
            post.remove("schedule")

    if state in ("playoffs", "offseason", "complete"):
        post.append("playoffs")

    post.append("draft")  # Results tab
    return post


# The tabs a viewer of a public league sees: the ones that read the same
# whoever is looking. Schedule, roster, lineup and strategy are one GM's own.
_VIEWER_TABS = (
    "standings",
    "power",
    "headlines",
    "leaders",
    "stats",
    "free-agents",
    "owner",
    "playoffs",
    "allstar",
)


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
        # Between seasons the newest season is still the one just played, so
        # once it has games behind it "today" is next spring, not this one.
        # (Opening day of the season just played would put every late-season
        # injury months in the future.)
        sr = SeasonRepository(db)
        row = sr.get_year(season_id)
        if row:
            year = row["year"]
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
    page: str | None = None,
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
                    # Free agent bids open, from the draft into the
                    # preseason (src/api/services/offseason_fa.py).
                    "fa_bidding": bool(league.get("fa_bidding"))
                    and league["state"] in ("draft", "preseason"),
                    # Several human GMs: the league advances by ready-check,
                    # so the Sim buttons give way to the ready bar.
                    "multiplayer": is_multiplayer(db, league_id),
                    # A league without injuries has no Until Injury button.
                    "injuries_enabled": injuries_allowed(league),
                    # A league that trades gets the trade stop boxes by the
                    # sim buttons.
                    "trades_enabled": trades_enabled_for(league),
                    # Salaries count (not Speed Blitz): budgets, prices, bids
                    # and the Expiring Deals tab.
                    "has_money": has_money(league),
                }
            )
            tabs = _compute_visible_tabs(league["state"], draft_complete)
            # The GM's expiring deals: from the champion's crowning until the
            # offseason runs (routers/free_agents.py expiring_tab).
            # Without money (Speed Blitz) they re-sign on their own.
            if (
                league["state"] == "offseason"
                and "free-agents" in tabs
                and has_money(league)
            ):
                tabs.insert(tabs.index("free-agents") + 1, "expiring")
            # Leagues that trade get a Trades tab once the draft is done, after
            # the lineup. It stays for the trade history once trades close.
            # The offseason window is open through the draft too, so it's
            # there before the draft is done in the offseason states.
            if (
                (draft_complete or league["state"] in OFFSEASON_STATES)
                and "lineup" in tabs
                and trades_enabled_for(league)
            ):
                tabs.insert(tabs.index("lineup") + 1, "trades")
                if not ctx["is_viewer"]:
                    # Offers and votes waiting on this GM: the tab's badge.
                    ctx["trade_inbox"] = trades.inbox_count(db, league_id, gm)
            # The Budget tab only where there are budgets (not Speed Blitz).
            if "budget" in tabs and not get_mode(league["mode"]).budgets:
                tabs.remove("budget")
            if ctx["is_viewer"]:
                tabs = _viewer_tabs(tabs, draft_complete)
                # A viewer of a public league that takes late joiners can
                # join between seasons: the top bar's Join button and the
                # banner over the tabs. A private league needs its join code.
                if gm.get("fired"):
                    # Their owner fired them (src/api/services/firing.py):
                    # the banner says so, and with re-entry on offers a new
                    # job between seasons.
                    uid = gm["user_id"]
                    ctx["fired"] = firing.latest(db, league_id, uid)
                    ctx["fired_reentry"] = bool(league["reentry_enabled"])
                    if not takeover.closed_reason(db, league, uid):
                        ctx["can_take_over"] = True
                        ctx["open_team_count"] = len(
                            takeover.open_teams(db, league_id, uid)
                        )
                elif (league["is_public"] or gm.get("has_code")) and not (
                    takeover.closed_reason(db, league)
                ):
                    ctx["can_take_over"] = True
                    ctx["open_team_count"] = len(takeover.open_teams(db, league_id))
            elif "headlines" in tabs and gm.get("id"):
                # Stories since the GM last opened the News tab: its badge.
                ctx["news_unseen"] = NewsRepository(db).count_unseen(
                    league_id, gm["id"]
                )
            if not ctx["is_viewer"] and "roster" in tabs and gm.get("team_id"):
                # Players who've asked to be traded: the Roster tab's badge.
                ctx["trade_wanted"] = HappinessRepository(
                    db, league_id
                ).team_trade_requests(gm["team_id"])
            if not ctx["is_viewer"] and "owner" in tabs and gm.get("id"):
                # Owner messages the GM hasn't read: the Owner tab's badge.
                ctx["owner_unseen"] = owner_office.unseen(db, gm["id"])
            # The team page (/welcome): the welcome screen in a league's
            # first season, the season preview after.
            ctx["team_page_label"] = (
                "Meet your team"
                if lr.count_seasons(league_id) <= 1
                else "Season preview"
            )
            # Now we have the state, so calculate visibility automatically
            ctx["visible_tabs"] = tabs
            # The top bar's season pill opens the league's settings.
            if league["state"] != "lobby":
                ctx["league_info"] = league_info(db, league)
                # The sidebar's Hall of Fame link, once there's been a vote.
                ctx["hall_of_fame"] = hall_of_fame.has_hall(db, league_id)
            if not ctx["is_viewer"]:
                mark_visit(db, league, active_tab)
                ctx["coach"] = coach_ctx(db, league)
                # A new league's getting-started bar, until the draft runs or
                # the GM first saves their roster.
                ctx["setup_bar"] = (
                    league["state"] != "lobby"
                    and not draft_complete
                    and gm.get("id") is not None
                    and GMRepository(db).needs_setup_bar(gm["id"])
                    and lr.count_seasons(league_id) == 1
                )

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
    # The top bar's next-move button. page is the page it's on (the last
    # part of the path), which decides between going to the next move and
    # doing it.
    if page is None:
        page = request.url.path.rstrip("/").rsplit("/", 1)[-1]
    # The offseason: once the GM has opened the season's summary, the
    # next-move button moves on to Expiring Deals and Begin Offseason, and
    # the summary stays a sidebar link.
    if (
        ctx["league_state"] == "offseason"
        and not ctx["is_viewer"]
        and gm.get("id")
        and ctx["season_id"]
    ):
        # The season summary page marks it (routers/seasons.py).
        ctx["summary_seen"] = GMRepository(db).summary_seen(gm["id"], ctx["season_id"])
        # With several GMs the button is the ready toggle, so the summary
        # and Expiring Deals ride beside it as pills (Josh, 2026-11-12), the
        # Expiring Deals one until the GM opens that tab.
        if ctx.get("multiplayer") and ctx["team_id"]:
            gms = GMRepository(db)
            seen = gms.expiring_seen(gm["id"], ctx["season_id"])
            if page == "expiring" and not seen:
                gms.mark_expiring_seen(gm["id"], ctx["season_id"])
                seen = True
            ctx["expiring_due"] = not seen
    weekend_ready = (
        as_phase == "done"
        and ctx["league_state"] == "season"
        and not ctx.get("multiplayer")
        and not ctx["is_viewer"]
        and bool(ctx["team_id"])
        and not all_star.person_drafting(db, league_id, ctx["season_id"])
    )
    # Where a Full Season run will stop next, for its note.
    stops = None
    if (
        ctx["league_state"] in ("preseason", "season")
        and not ctx.get("multiplayer")
        and not ctx["is_viewer"]
        and ctx["team_id"]
        and ctx["season_id"]
    ):
        row = GameRepository(db).get_next_unplayed_date(ctx["season_id"])
        deadline = (
            deadline_date(db, ctx["season_id"]) if ctx.get("trades_enabled") else None
        )
        # Past deadline day no team can offer a trade, so the sim menu drops
        # its trade boxes (Josh, 2026-11-10).
        ctx["trades_closed"] = bool(deadline and row and row["game_date"] > deadline)
        stops = next_move.sim_stops(
            row["game_date"] if row else None,
            # The tab's phase is "none" in the preseason; the vote is ahead.
            as_phase
            if ctx["league_state"] == "season"
            else all_star.phase(db, ctx["season_id"]),
            all_star.window(db, ctx["season_id"]),
            deadline,
            GameRepository(db).last_scheduled_date(ctx["season_id"]),
        )
    # The preseason's last chance to set the front office and ticket prices
    # before they lock: until the GM opens the Budget tab, the next move
    # sends them there.
    if (
        ctx["league_state"] == "preseason"
        and not ctx["is_viewer"]
        and ctx["team_id"]
        and "budget" in (ctx.get("visible_tabs") or [])
    ):
        year = ContractRepository(db).current_year(league_id)
        ctx["budget_due"] = year is not None and not BudgetRepository(db).budget_seen(
            league_id, ctx["team_id"], year
        )
    # Then the Roster and Lineup tabs, once each before Opening Day (Josh,
    # 2026-11-10): opening one marks it, so the button moves on from there.
    if (
        ctx["league_state"] == "preseason"
        and not ctx["is_viewer"]
        and ctx["team_id"]
        and gm.get("id")
        and ctx["season_id"]
    ):
        gms = GMRepository(db)
        seen = gms.preseason_seen(gm["id"], ctx["season_id"])
        # While free agent bids are open the signings are still to come, so
        # a look at the Roster or Lineup doesn't count yet.
        if (
            page in gms.PRESEASON_TABS
            and page not in seen
            and not ctx.get("fa_bidding")
        ):
            gms.mark_preseason_seen(gm["id"], ctx["season_id"], page)
            seen.add(page)
        ctx["roster_due"] = "roster" not in seen
        ctx["lineup_due"] = "lineup" not in seen
        ctx["strategy_due"] = "strategy" not in seen
        # Multiplayer pills (Josh, 2026-11-14): Roster and Lineup until saved
        # this preseason, not just opened.
        if ctx.get("multiplayer"):
            saved = gms.preseason_saved(gm["id"], ctx["season_id"])
            ctx["roster_save_due"] = "roster" not in saved
            ctx["lineup_save_due"] = "lineup" not in saved
    # A multiplayer draft: the Draft tab, then the Free Agents tab (bids),
    # each once (Josh, 2026-11-12). The button is the ready toggle there, so
    # these ride beside it as pills; opening a tab marks it.
    if (
        ctx["league_state"] == "draft"
        and ctx.get("multiplayer")
        and not ctx["is_viewer"]
        and ctx["team_id"]
        and gm.get("id")
        and ctx["season_id"]
    ):
        gms = GMRepository(db)
        seen = gms.draft_seen(gm["id"], ctx["season_id"])
        if page in gms.DRAFT_TABS and page not in seen:
            gms.mark_draft_seen(gm["id"], ctx["season_id"], page)
            seen.add(page)
        ctx["draft_tab_due"] = "draft" not in seen
        ctx["fa_tab_due"] = "free-agents" not in seen
    # After a trade brings players in, the Roster tab, where they move up to
    # the 40-man (Josh, 2026-11-11). Opening it clears that.
    if (
        ctx["league_state"] in ("preseason", "season")
        and not ctx["is_viewer"]
        and ctx["team_id"]
        and gm.get("id")
        and ctx["season_id"]
    ):
        gms = GMRepository(db)
        if page == "roster":
            gms.clear_trade_roster_due(gm["id"])
        else:
            ctx["trade_roster_due"] = gms.trade_roster_due(gm["id"], ctx["season_id"])
    ctx["next_move"] = next_move.pick(ctx, page, weekend_ready, stops)
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
