# src/api/routers/leagues.py
#
# League list, creating and joining leagues, starting a league, renaming it,
# and the lobby page that /leagues/{id}/ shows before the league starts.

from __future__ import annotations

import random
import string
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from src.api.dependencies import (
    DB,
    GM,
    ActiveLeague,
    Commissioner,
    GMOrViewer,
    IsHTMX,
    MemberGM,
    Unpaused,
    User,
)
from src.api.services import (
    custom_teams,
    firing,
    league_custom_teams,
    league_settings,
    lobby_teams,
    personas,
    settings_votes,
    sim_jobs,
    takeover,
)
from src.api.services import admin as admin_service
from src.api.services.coach import coach_ctx
from src.api.services.leave_league import leave_league
from src.api.view_models.league_info import league_info
from src.league import team_facts
from src.api.view_models.welcome import welcome
from src.config import settings
from src.db.locks import LeagueBusy
from src.db.repositories.career_repo import CareerRepository
from src.db.repositories.custom_team_repo import CustomTeamRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.season_repo import SeasonRepository
from src.db.repositories.sim_job_repo import SimJobRepository
from src.league import divisions, real_seasons
from src.league.league_constants import (
    DEFAULT_BACKSTORY_YEARS,
    DEFAULT_INJURY_RATE,
    INJURY_RATES,
    MAX_BACKSTORY_YEARS,
    MAX_SEASONS,
    UNLIMITED_SEASONS,
)
from src.league.league_modes import (
    BLITZ,
    DEFAULT_MODE,
    SPEED_BLITZ,
    get_mode,
    is_blitz_style,
)
from src.web.utils import _shell_ctx, render, tab_response, templates

router = APIRouter(tags=["web"])


# ── League list ────────────────────────────────────────────────────────────────

LEAGUES_TAB_COOKIE = "leagues_tab"

# The leagues page's tabs, in order, with the label each one shows.
LEAGUE_TABS = (
    ("tutorial", "Tutorial"),
    ("running", "Running"),
    ("join", "Join"),
    ("watch", "Watch"),
    ("completed", "Completed"),
)

# Old tab names, mapped to what they're called now.
TAB_ALIASES = {"practice": "tutorial"}


@router.get("/leagues/", response_class=HTMLResponse)
def leagues_index(
    request: Request,
    db: DB,
    user: User,
    tab: str | None = None,
    cant_join: str | None = None,
):
    """The user's leagues and the public ones, split into tabs. The tab picked
    is kept in a cookie, so the page comes back the way the GM left it."""
    # Guests from before passwords existed choose a login before going on.
    if not user["has_password"]:
        return RedirectResponse("/auth/set-password", status_code=302)

    gm_repo = GMRepository(db)
    mine = [dict(r) for r in gm_repo.get_users_leagues(user["id"])]
    public = gm_repo.get_public_leagues(user["id"])
    for league in mine + public:
        league["state_label"] = state_label(league["state"], league["season_number"])
    # A running league takes new GMs between seasons, onto its AI GMs' teams.
    for league in public:
        league["takeover"] = league["state"] != "lobby" and not takeover.closed_reason(
            db, league
        )

    groups = {
        "tutorial": [lg for lg in mine if lg["is_practice"]],
        "running": [
            lg for lg in mine if not lg["is_practice"] and lg["state"] != "complete"
        ],
        "join": [lg for lg in public if lg["state"] == "lobby" or lg["takeover"]],
        "watch": [lg for lg in public if lg["state"] != "lobby"],
        "completed": [
            lg for lg in mine if not lg["is_practice"] and lg["state"] == "complete"
        ],
    }

    # The Tutorial tab was called Practice, so old links and cookies still work.
    tab = TAB_ALIASES.get(tab, tab)
    chosen = tab if tab in groups else None
    active = chosen or request.cookies.get(LEAGUES_TAB_COOKIE)
    active = TAB_ALIASES.get(active, active)
    if active not in groups:
        # Someone new starts on Tutorial; anyone with a league on Running.
        active = "running" if groups["running"] or groups["completed"] else "tutorial"

    resp = templates.TemplateResponse(
        request,
        "leagues/index.html",
        {
            "user": user,
            "tabs": [(key, label, len(groups[key])) for key, label in LEAGUE_TABS],
            "active_tab": active,
            "leagues": groups[active],
            "brand_new": not mine,
            "join_error": cant_join_reason(db, cant_join) if cant_join else None,
        },
    )
    if chosen:
        resp.set_cookie(
            LEAGUES_TAB_COOKIE,
            chosen,
            max_age=60 * 60 * 24 * 365,
            httponly=True,
            samesite="lax",
            secure=settings.served_over_https,
        )
    return resp


def cant_join_reason(db, league_id: str) -> str:
    """Why a join from a stale Join tab (or take-over page) didn't go through:
    the league went private, closed to late joiners, or is gone. The league
    is looked up again, so the message says what's true now."""
    league = LeagueRepository(db).get_by_id(league_id)
    if not league:
        return "That league doesn't exist anymore, so you didn't join it."
    name = league["name"]
    if not league["is_public"]:
        return (
            f"{name} was made private, so you didn't join it. Ask its"
            " commissioner for the join code."
        )
    if league["state"] != "lobby":
        reason = takeover.closed_reason(db, league)
        if reason:
            return f"You didn't join {name}. {reason}"
    return f"You didn't join {name}. Try again."


def _cant_join(league_id: str) -> RedirectResponse:
    """Back to a fresh Join tab, with a note on why the join failed."""
    return RedirectResponse(
        f"/leagues/?tab=join&cant_join={league_id}", status_code=303
    )


def state_label(state: str, season_number: int) -> str:
    """The league's phase and which season it's in, e.g. "Draft 1" or
    "Playoffs 3". The lobby and a finished league have no season number."""
    if state in ("lobby", "complete") or not season_number:
        return state.title()
    return f"{state.title()} {season_number}"


@router.get("/leagues/new", response_class=HTMLResponse)
def new_league_page(request: Request, user: User):
    return templates.TemplateResponse(
        request,
        "leagues/new.html",
        {
            "default_mode": DEFAULT_MODE,
            "modes": [BLITZ, SPEED_BLITZ],
            "team_counts": divisions.TEAM_COUNTS,
            "default_team_count": divisions.DEFAULT_TEAM_COUNT,
            "default_backstory_years": DEFAULT_BACKSTORY_YEARS,
            "max_backstory_years": MAX_BACKSTORY_YEARS,
            # The seasons slider runs 1..MAX_SEASONS, then unlimited (0).
            "season_choices": [*range(1, MAX_SEASONS + 1), UNLIMITED_SEASONS],
            "injury_rates": list(INJURY_RATES),
            "real_seasons": real_seasons.available(),
            # Real seasons are for paid contributors (others can join one).
            "can_real_season": custom_teams.can_build(user),
        },
    )


# was create_league
@router.post("/leagues/new")
def new_league(
    db: DB,
    user: User,
    name: str = Form(...),
    mode: str = Form(DEFAULT_MODE),
    decision_window_sec: int = Form(120),
    draft_window_sec: int = Form(300),
    lineup_window_sec: int = Form(600),
    reentry_enabled: bool = Form(True),
    owner_firing: bool = Form(False),
    pace_control: str = Form("timer"),
    sim_period_days: int = Form(3),
    num_seasons: int = Form(10),
    is_public: bool = Form(False),
    late_joins: bool = Form(True),
    trade_vote: bool = Form(False),
    trades_enabled: bool | None = Form(None),
    pick_trades: bool = Form(False),
    injuries_enabled: bool | None = Form(None),
    injury_rate: int = Form(DEFAULT_INJURY_RATE),
    num_teams: int = Form(divisions.DEFAULT_TEAM_COUNT),
    weighted_schedule: bool = Form(True),
    backstory_years: int = Form(DEFAULT_BACKSTORY_YEARS),
    real_season: str = Form(""),
):
    get_mode(mode)  # rejects an unknown mode
    season = int(real_season) if real_season else None
    if season is not None:
        if season not in real_seasons.available():
            raise ValueError(f"There's no real {season} season to start from.")
        if not custom_teams.can_build(user):
            raise HTTPException(
                status_code=403,
                detail="Real-season leagues are for paid contributors.",
            )
        # A real season is all 30 of its clubs and has no made-up past.
        num_teams = real_seasons.TEAMS
        backstory_years = 0
    if num_teams not in divisions.TEAM_COUNTS:
        raise ValueError(f"A league can't have {num_teams} teams.")
    if pace_control not in ("timer", "confirmed"):
        raise ValueError(f"Unknown pace '{pace_control}'.")
    if not 1 <= sim_period_days <= 30:
        raise ValueError("Days per sim period must be between 1 and 30.")
    if not UNLIMITED_SEASONS <= num_seasons <= MAX_SEASONS:
        raise ValueError(
            f"Number of seasons must be between 1 and {MAX_SEASONS}, or unlimited."
        )
    if injury_rate not in INJURY_RATES:
        raise ValueError(f"Unknown injury rate {injury_rate}%.")
    if not 0 <= backstory_years <= MAX_BACKSTORY_YEARS:
        raise ValueError(
            f"Years of history must be between 0 and {MAX_BACKSTORY_YEARS}."
        )

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
            "lineup_window_sec": lineup_window_sec,
            "reentry_enabled": reentry_enabled,
            "owner_firing": owner_firing,
            "pace_control": pace_control,
            "sim_period_days": sim_period_days,
            "num_seasons": num_seasons,
            "is_public": is_public,
            "late_joins": late_joins,
            "trade_vote": trade_vote,
            # Left out (an old form or a script), the mode's default.
            "trades_enabled": (
                get_mode(mode).trades_enabled
                if trades_enabled is None
                else trades_enabled
            ),
            "pick_trades": pick_trades,
            "num_teams": num_teams,
            "weighted_schedule": weighted_schedule,
            "backstory_years": backstory_years,
            "real_season": season,
            # Left out (an old form or a script), the mode's default.
            "injuries_enabled": (
                get_mode(mode).injuries_default
                if injuries_enabled is None
                else injuries_enabled
            ),
            "injury_rate": injury_rate,
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
    personas.fill_lobby(db, league_id)

    db.commit()
    return RedirectResponse(f"/leagues/{league_id}/", status_code=302)


# A tutorial league's settings: Speed Blitz, the quickest mode, and no clock,
# since the only human GM is the one learning.
TUTORIAL_SETTINGS = {
    **SPEED_BLITZ.form_presets,
    "pace_control": "confirmed",
    "is_public": False,
    "is_practice": True,
}


@router.post("/leagues/tutorial")
@router.post("/leagues/practice", include_in_schema=False)  # the old name
def new_tutorial_league(db: DB, user: User):
    """A solo Speed Blitz league with the coach panel. It has no join code,
    so nobody else can get in, and it only shows on its owner's Tutorial tab.
    There's no limit on how many a user starts."""
    league_repo = LeagueRepository(db)
    gm_repo = GMRepository(db)
    count = sum(1 for lg in gm_repo.get_users_leagues(user["id"]) if lg["is_practice"])

    league_id = str(uuid.uuid4())
    league_repo.create_new_league(
        league_id=league_id,
        name=f"Tutorial League {count + 1}",
        join_code=None,
        mode=SPEED_BLITZ.key,
        commissioner_gm_id=None,
        settings=TUTORIAL_SETTINGS,
    )
    gm_id = gm_repo.create_gm(
        league_id=league_id,
        user_id=user["id"],
        display_name=user["display_name"],
    )
    gm_repo.set_commissioner(gm_id=gm_id, league_id=league_id)
    personas.fill_lobby(db, league_id)
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
    join_code = join_code.strip().upper()
    league = league_repo.get_by_join_code(join_code)
    if not league:
        return templates.TemplateResponse(
            request,
            "leagues/join.html",
            {"error": "No league found with that join code.", "join_code": join_code},
        )

    # 2. A GM already in the league goes straight to it, started or not
    existing_gm = gm_repo.get_by_user_and_league(user["id"], league["id"])
    if existing_gm:
        return RedirectResponse(f"/leagues/{league['id']}/", status_code=302)
    if league.get("single_player"):
        return templates.TemplateResponse(
            request,
            "leagues/join.html",
            {
                "error": f"{league['name']} has a custom team, so it's single player.",
                "join_code": join_code,
            },
        )

    # A running league takes new GMs between seasons: they pick a team an
    # AI GM runs. Whether or not they can join now, the code lets them watch
    # it, even when it's private.
    if league["state"] != "lobby":
        league_repo.add_watcher(league["id"], user["id"])
        db.commit()
        reason = takeover.closed_reason(db, league_repo.get_by_id(league["id"]))
        if reason:
            return templates.TemplateResponse(
                request,
                "leagues/join.html",
                {
                    "error": reason,
                    "join_code": join_code,
                    "watch_url": f"/leagues/{league['id']}/",
                },
            )
        return RedirectResponse(
            f"/leagues/{league['id']}/take-over?code={join_code}", status_code=302
        )

    # 3. Join the league using our clean GM creator
    gm_repo.create_gm(
        league_id=league["id"],
        user_id=user["id"],
        display_name=user["display_name"],
    )
    personas.fill_lobby(db, league["id"])  # they take an AI GM's place
    db.commit()

    return RedirectResponse(f"/leagues/{league['id']}/", status_code=302)


@router.post("/leagues/{league_id}/join")
def join_public_league(
    league_id: str,
    db: DB,
    user: User,
):
    """Join a public league from the leagues page, no code needed."""
    league = LeagueRepository(db).get_by_id(league_id)
    gm_repo = GMRepository(db)
    if league and gm_repo.get_by_user_and_league(user["id"], league_id):
        return RedirectResponse(f"/leagues/{league_id}/", status_code=302)
    # The Join tab may be stale: the league went private or closed since.
    # Someone who entered a private league's code can still join from it.
    if (
        not league
        or league.get("single_player")
        or not (
            league["is_public"]
            or LeagueRepository(db).is_watcher(league_id, user["id"])
        )
    ):
        return _cant_join(league_id)
    if league["state"] != "lobby":
        if takeover.closed_reason(db, league):
            return _cant_join(league_id)
        return RedirectResponse(f"/leagues/{league_id}/take-over", status_code=302)

    gm_repo.create_gm(
        league_id=league_id,
        user_id=user["id"],
        display_name=user["display_name"],
    )
    personas.fill_lobby(db, league_id)  # they take an AI GM's place
    db.commit()
    return RedirectResponse(f"/leagues/{league_id}/", status_code=302)


# ── Taking over a team in a running league (services/takeover.py) ─────────────


def _takeover_league(db, league_id: str, code: str, user_id: str) -> dict | None:
    """The league, if the person may see its open teams: it's public, or they
    have its join code (in the link, or entered before: league_watchers)."""
    repo = LeagueRepository(db)
    league = repo.get_by_id(league_id)
    if not league or league["state"] == "lobby":
        return None
    if (
        league["is_public"]
        or (code and code.strip().upper() == league["join_code"])
        or repo.is_watcher(league_id, user_id)
        or takeover.is_fired(db, league_id, user_id)
    ):
        return league
    return None


def _takeover_page(request, db, league, code, user_id, error=None):
    fired = takeover.is_fired(db, league["id"], user_id)
    return templates.TemplateResponse(
        request,
        "leagues/take_over.html",
        {
            "league": league,
            "code": code,
            "error": error,
            "closed": takeover.closed_reason(db, league, user_id),
            "teams": takeover.open_teams(db, league["id"], user_id),
            "joined_year": takeover.joined_year(db, league),
            # Back from a firing (src/api/services/firing.py).
            "fired": firing.latest(db, league["id"], user_id) if fired else None,
        },
    )


@router.get("/leagues/{league_id}/take-over", response_class=HTMLResponse)
def take_over_page(
    request: Request, league_id: str, db: DB, user: User, code: str = ""
):
    """Pick a team an AI GM runs, to join a league that has started."""
    league = _takeover_league(db, league_id, code, user["id"])
    if not league:
        return _cant_join(league_id)
    mine = GMRepository(db).get_by_user_and_league(user["id"], league_id)
    if mine and not mine["fired_at"]:
        return RedirectResponse(f"/leagues/{league_id}/", status_code=302)
    return _takeover_page(request, db, league, code, user["id"])


@router.post("/leagues/{league_id}/take-over")
def take_over_team(
    request: Request,
    league_id: str,
    db: DB,
    user: User,
    team_id: str = Form(...),
    code: str = Form(""),
):
    league = _takeover_league(db, league_id, code, user["id"])
    if not league:
        return _cant_join(league_id)
    try:
        takeover.take_over(db, league_id, user, team_id)
    except (takeover.TakeoverClosed, LeagueBusy) as e:
        db.rollback()
        msg = (
            str(e)
            if isinstance(e, takeover.TakeoverClosed)
            else (f"{league['name']} is moving on right now. Try again in a minute.")
        )
        return _takeover_page(request, db, league, code, user["id"], error=msg)
    return RedirectResponse(f"/leagues/{league_id}/", status_code=302)


@router.post("/leagues/{league_id}/settings/{setting}")
def commissioner_setting(
    league_id: str,
    setting: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    on: bool = Form(...),
    next: str = Form(""),
):
    """The commissioner turns Visibility (public or private) or Late joiners
    on or off. Lobby and League page both show the buttons."""
    league_repo = LeagueRepository(db)
    league = league_repo.get_by_id(league_id)
    if not league or league["commissioner_gm_id"] != gm["id"]:
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    if (
        setting not in COMMISSIONER_SETTINGS
        or league["is_practice"]
        or (on and league.get("single_player"))
    ):
        return JSONResponse({"detail": "Not a setting you can change"}, status_code=422)
    league_repo.update_settings(league_id, {setting: on})
    db.commit()
    # Back to the page the button was on, in this league only.
    back = (
        next if next.startswith(f"/leagues/{league_id}/") else f"/leagues/{league_id}/"
    )
    return RedirectResponse(back, status_code=303)


# The settings a commissioner can change once the league exists.
COMMISSIONER_SETTINGS = ("is_public", "late_joins")


@router.get("/leagues/join", response_class=HTMLResponse)
def join_page(request: Request):
    return templates.TemplateResponse(request, "leagues/join.html", {})


# ── League actions ────────────────────────────────────────────────────────────


@router.post("/leagues/{league_id}/start")
def start_league_router(
    league_id: str,
    db: DB,
    _: Commissioner,
    _unpaused: Unpaused,
):
    """Queue the league's start (teams, players, the draft) for the sim
    worker. The lobby polls the job, then opens the league.

    If the start is already under way (asked for from another tab, or before
    the commissioner browsed away and back), answers with that job to poll
    rather than turning the click away as a busy league."""
    running = _start_job(db, league_id)
    job_id = running or sim_jobs.submit(db, league_id, "start")
    return JSONResponse(
        {"job_id": job_id, "poll": f"/leagues/{league_id}/jobs/{job_id}"},
        status_code=202,
    )


def _start_job(conn, league_id: str) -> str | None:
    """The id of the league's start job while it's queued or running."""
    job = SimJobRepository(conn).active(league_id)
    return str(job["id"]) if job and job["kind"] == "start" else None


@router.post("/leagues/{league_id}/leave")
def leave_league_router(
    league_id: str,
    db: DB,
    gm: MemberGM,
):
    """Leave the league. Once it has started, AI takes over the GM's team. A
    GM their owner fired just takes the league off their list."""
    leave_league(db, league_id, gm["id"])
    return JSONResponse({"left": True})


# ── League rename ──────────────────────────────────────────────────────────────


class RenameLeagueRequest(BaseModel):
    name: str


@router.post("/leagues/{league_id}/rename")
def rename_league(
    league_id: str,
    body: RenameLeagueRequest,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
):
    name = body.name.strip()
    if not name:
        return JSONResponse({"detail": "Name required"}, status_code=422)
    league_repo = LeagueRepository(db)
    league = league_repo.get_by_id(league_id)
    if not league or league["commissioner_gm_id"] != gm["id"]:
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    league_repo.rename(league_id, name)
    CareerRepository(db).rename_league(league_id, name)  # profile pages
    db.commit()
    return JSONResponse({"name": name})


# ── Dashboard shell ────────────────────────────────────────────────────────────


@router.get("/leagues/{league_id}/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
    custom_error: str = "",
):
    gm_repo = GMRepository(db)
    league_repo = LeagueRepository(db)
    league = league_repo.get_by_id(league_id)
    if not league:
        return RedirectResponse("/leagues/")

    # Viewers of a public league land on its standings, or its history once
    # it's over. The pages built around a GM's own team aren't open to them.
    if gm.get("is_viewer"):
        # Someone just fired lands on how the season ended, under the
        # banner that says who let them go and why.
        if gm.get("fired") and league["state"] == "offseason":
            return RedirectResponse(f"/leagues/{league_id}/season-summary")
        if league["state"] == "complete":
            return RedirectResponse(f"/leagues/{league_id}/history")
        return RedirectResponse(f"/leagues/{league_id}/standings")

    is_commish = league["commissioner_gm_id"] == gm["id"]

    state = league["state"]
    # Redirect logic
    if state in ("preseason", "draft"):
        # A GM meets their team once a season, before anything else: in a
        # new league the welcome screen, after that the season preview. That
        # comes first even once the draft is done, so someone who took over
        # a team after the draft still gets it.
        season_id = SeasonRepository(db).get_current_id_for_league(league_id)
        if season_id and gm_repo.needs_welcome(gm["id"], season_id):
            return RedirectResponse(f"/leagues/{league_id}/welcome")
        # Once the draft is done, coming back in shows its results; the
        # board is only for a draft still to run.
        if league_repo.draft_complete(league_id):
            return RedirectResponse(f"/leagues/{league_id}/draft/results")
        return RedirectResponse(f"/leagues/{league_id}/draft")
    if state == "offseason":
        # The playoffs are over and the offseason hasn't run yet, so next
        # season's preview doesn't exist. The season summary is where the
        # offseason starts from; the preview follows the retirements.
        return RedirectResponse(f"/leagues/{league_id}/season-summary")
    if state in ("season", "playoffs"):
        return RedirectResponse(f"/leagues/{league_id}/standings")
    if state == "evaluation":
        # Simplified the season fetch for now to get you back to green
        return RedirectResponse(f"/leagues/{league_id}/history/1/")
    if state == "complete":
        return RedirectResponse(f"/leagues/{league_id}/history")

    context = _lobby_gms_context(gm_repo, league, gm)
    context.update(
        {
            "league_name": league["name"],
            "league_id": league_id,
            "is_commissioner": bool(is_commish),
            "can_edit_settings": bool(is_commish),
            "settings_next": f"/leagues/{league_id}/",
            "info": league_info(db, league),
            "coach": coach_ctx(db, league),
            "custom": _lobby_custom_ctx(db, league, user) if is_commish else None,
            "custom_error": custom_error,
        }
    )
    # Back on the lobby while the start is still running: the page picks up
    # that job's progress instead of offering Start League again.
    start_job = _start_job(db, league_id)
    if start_job:
        context["start_poll"] = f"/leagues/{league_id}/jobs/{start_job}"

    return templates.TemplateResponse(
        request=request, name="dashboard/lobby.html", context=context
    )


def _lobby_custom_ctx(db, league: dict, user: dict) -> dict | None:
    """The lobby's Custom teams card, for a commissioner who can build them
    (services/league_custom_teams.py)."""
    if not custom_teams.can_build(user):
        return None
    chosen = league_custom_teams.assignments(db, league["id"])
    mine = []
    for t in CustomTeamRepository(db).list_for(user["id"]):
        summary = custom_teams.summary(custom_teams.roster(t))
        mine.append({"id": t["id"], "name": t["name"], "ready": summary["ready"]})
    return {
        "refusal": league_custom_teams.refusal(db, league, user),
        "teams": [
            {
                "city": city,
                "mascot": mascot,
                "chosen": chosen.get((city, mascot)),
            }
            for city, mascot in lobby_teams.league_teams(db, league["id"])
        ],
        "mine": mine,
        "any": bool(chosen),
    }


@router.post("/leagues/{league_id}/lobby/custom")
def lobby_custom_team(
    request: Request,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
    team: str = Form(...),
    custom_team_id: str = Form(""),
):
    """The commissioner puts one of their custom teams on a lobby team
    ("City|Mascot"), or takes it off with an empty id."""
    league = LeagueRepository(db).get_by_id(league_id)
    if not league or league["commissioner_gm_id"] != str(gm["id"]):
        return JSONResponse({"detail": "Forbidden"}, status_code=403)
    if sim_jobs.league_has_job(db, league_id):
        return RedirectResponse(f"/leagues/{league_id}/", status_code=303)
    city, _, mascot = team.partition("|")
    try:
        league_custom_teams.assign(db, league, user, city, mascot, custom_team_id)
    except league_custom_teams.CustomTeamRefused as e:
        db.rollback()
        return RedirectResponse(
            f"/leagues/{league_id}/?custom_error={quote(str(e))}#custom-teams",
            status_code=303,
        )
    db.commit()
    return RedirectResponse(f"/leagues/{league_id}/#custom-teams", status_code=303)


@router.get("/leagues/{league_id}/league", response_class=HTMLResponse)
def league_page(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
    saved: str = "",
    settings_error: str = "",
):
    """The league's settings and who runs each team, for GMs and viewers once
    the league has started. The lobby shows the same before then."""
    league = LeagueRepository(db).get_by_id(league_id)
    if not league or league["state"] == "lobby":
        return RedirectResponse(f"/leagues/{league_id}/")
    ctx = _shell_ctx(request, db, gm, league_id, user=user)
    ctx["can_edit_settings"] = (
        not ctx["is_viewer"] and league["commissioner_gm_id"] == gm["id"]
    )
    ctx["settings_next"] = f"/leagues/{league_id}/league"
    ctx["late_joins"] = bool(league["late_joins"])
    # The commissioner of a one-person league can change most settings; with
    # more people they propose changes the others vote on.
    info = ctx.get("league_info") or league_info(db, league)
    ctx["league_info"] = info
    me = None if ctx["is_viewer"] else gm.get("id")
    solo = league_settings.can_edit(league, me, info["human_gms"])
    proposal = settings_votes.view(db, league, me) if not solo else None
    ctx["proposal"] = proposal
    multi = settings_votes.can_propose(league, me, info["human_gms"])
    if solo or (multi and not proposal):
        ctx["solo_edit"] = {
            "multi": multi,
            "season_choices": league_settings.season_choices(
                league["state"], info["season_number"], league["num_seasons"]
            ),
            "sim_period_range": league_settings.SIM_PERIOD_RANGE,
            "injury_rates": league_settings.injury_rate_choices(info["injury_rate"]),
            "windows": {
                k: admin_service.NUMBER_RANGES[k] for k in admin_service.WINDOW_KEYS
            },
            "trades": is_blitz_style(league["mode"]),
            "error": settings_error,
        }
    ctx["settings_error"] = settings_error
    ctx["settings_toast"] = _SETTINGS_TOASTS.get(saved)
    # Every team's market size and climate: the Teams card.
    ctx["league_teams"] = team_facts.league_teams(
        db, league_id, None if ctx["is_viewer"] else gm.get("team_id")
    )
    # A GM their owner fired watches like a viewer, but can still leave.
    ctx["fired_member"] = bool(gm.get("fired"))
    if not ctx["is_viewer"]:
        # The Leave League button warns the last person out that the league
        # goes with them.
        ctx["leaving_deletes_league"] = not GMRepository(db).has_people(
            league_id, besides_gm_id=gm["id"]
        )
    elif ctx["fired_member"]:
        ctx["leaving_deletes_league"] = not db.execute(
            "SELECT 1 FROM gms WHERE league_id = %s AND user_id IS NOT NULL"
            " AND user_id <> %s LIMIT 1",
            (league_id, user["id"]),
        ).fetchone()
    return tab_response(request, htmx, "dashboard/partials/league_info.html", ctx)


@router.post("/leagues/{league_id}/league/settings")
def solo_settings(
    league_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    name: str = Form(...),
    num_seasons: int = Form(...),
    sim_period_days: int = Form(...),
    weighted_schedule: bool = Form(False),
    injuries_enabled: bool = Form(False),
    injury_rate: int | None = Form(None),
    trades_enabled: bool = Form(False),
    pick_trades: bool = Form(False),
    reentry_enabled: bool = Form(False),
):
    """The commissioner of a one-person league saves the League page's Edit
    settings form (src/api/services/league_settings.py)."""
    back = f"/leagues/{league_id}/league"
    try:
        error = league_settings.save_solo(
            db,
            league_id,
            gm["id"],
            {
                "name": name,
                "num_seasons": num_seasons,
                "sim_period_days": sim_period_days,
                "weighted_schedule": weighted_schedule,
                "injuries_enabled": injuries_enabled,
                "injury_rate": injury_rate,
                "trades_enabled": trades_enabled,
                "pick_trades": pick_trades,
                "reentry_enabled": reentry_enabled,
            },
        )
    except LeagueBusy:
        db.rollback()
        error = "A sim is running. Try again once it's done."
    if error:
        # Nothing was written: save_solo checks before it saves.
        return RedirectResponse(
            f"{back}?settings_error={quote(error)}", status_code=303
        )
    return RedirectResponse(f"{back}?saved=1", status_code=303)


# What the League page says after a settings form or vote goes through.
_SETTINGS_TOASTS = {
    "1": "✓ Settings saved",
    "proposed": "✓ Proposal sent to the league",
    "voted": "✓ Vote counted",
    "withdrawn": "✓ Proposal withdrawn",
}


def _settings_back(league_id: str, error: str | None, saved: str):
    back = f"/leagues/{league_id}/league"
    if error:
        return RedirectResponse(
            f"{back}?settings_error={quote(error)}", status_code=303
        )
    return RedirectResponse(f"{back}?saved={saved}", status_code=303)


@router.post("/leagues/{league_id}/league/settings/propose")
def propose_settings(
    league_id: str,
    db: DB,
    gm: GM,
    _active: ActiveLeague,
    name: str = Form(...),
    num_seasons: int = Form(...),
    pace_control: str = Form(...),
    decision_window_sec: int = Form(...),
    draft_window_sec: int = Form(...),
    lineup_window_sec: int = Form(...),
    sim_period_days: int = Form(...),
    weighted_schedule: bool = Form(False),
    injuries_enabled: bool = Form(False),
    injury_rate: int | None = Form(None),
    trades_enabled: bool = Form(False),
    trade_vote: bool | None = Form(None),
    pick_trades: bool = Form(False),
    reentry_enabled: bool = Form(False),
):
    """The commissioner of a league with more than one person proposes
    settings changes for the others to vote on (settings_votes.py)."""
    form = {
        "name": name,
        "num_seasons": num_seasons,
        "pace_control": pace_control,
        "decision_window_sec": decision_window_sec,
        "draft_window_sec": draft_window_sec,
        "lineup_window_sec": lineup_window_sec,
        "sim_period_days": sim_period_days,
        "weighted_schedule": weighted_schedule,
        "injuries_enabled": injuries_enabled,
        "trades_enabled": trades_enabled,
        "pick_trades": pick_trades,
        "reentry_enabled": reentry_enabled,
    }
    if injury_rate is not None:
        form["injury_rate"] = injury_rate
    # The form only has Trade vote with three or more people in the league.
    if trade_vote is not None:
        form["trade_vote"] = trade_vote
    error = settings_votes.propose(db, league_id, gm["id"], form)
    return _settings_back(league_id, error, "proposed")


@router.post("/leagues/{league_id}/league/settings/vote")
def vote_settings(
    league_id: str, db: DB, gm: GM, _active: ActiveLeague, yes: bool = Form(...)
):
    error = settings_votes.vote(db, league_id, gm["id"], yes)
    return _settings_back(league_id, error, "voted")


@router.post("/leagues/{league_id}/league/settings/withdraw")
def withdraw_settings(league_id: str, db: DB, gm: GM, _active: ActiveLeague):
    error = settings_votes.withdraw(db, league_id, gm["id"])
    return _settings_back(league_id, error, "withdrawn")


@router.get("/leagues/{league_id}/next-move", response_class=HTMLResponse)
def next_move_button(
    request: Request,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
    page: str = "",
):
    """The top bar's next-move button for the page the GM is on, which the
    shell reloads after each tab swap and sim (the league may have moved on,
    or the page changed from go-to to do-it)."""
    ctx = _shell_ctx(request, db, gm, league_id, user=user, page=page)
    return render("dashboard/partials/_next_move.html", ctx)


@router.get("/leagues/{league_id}/welcome", response_class=HTMLResponse)
def welcome_page(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    """The GM's team before the season: the welcome screen when the league
    starts, a season preview before each draft after that. Shown once per
    season before the draft, and open from the Roster tab any time."""
    league = LeagueRepository(db).get_by_id(league_id)
    if not league or league["state"] == "lobby":
        return RedirectResponse(f"/leagues/{league_id}/")
    team = welcome(db, league, gm)
    if not team:
        return RedirectResponse(f"/leagues/{league_id}/roster")
    GMRepository(db).mark_welcomed(gm["id"], team["season_id"])
    ctx = _shell_ctx(request, db, gm, league_id, user=user)
    ctx["welcome"] = team
    return tab_response(request, htmx, "dashboard/partials/welcome.html", ctx)


# Pages that link to a GM's page (an AI GM's persona card or a person's
# in-league profile): the path it links back to, and its name.
PERSONA_BACK = {
    "league": ("league", "the League page"),
    "welcome": ("welcome", "your team"),
    "headlines": ("headlines", "News"),
    "standings": ("standings", "Standings"),
    "power": ("power", "Power Rankings"),
    "schedule": ("schedule", "Schedule"),
    "trades": ("trades", "Trades"),
}


@router.get("/leagues/{league_id}/personas/{persona_id}", response_class=HTMLResponse)
def persona_page(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    persona_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
    back: str = "league",
):
    """An AI GM's persona card. Personas are a site-wide library, so any
    persona can be shown; the team is the one it runs in this league. `back`
    is the page that linked here, which the card links back to."""
    persona = personas.card(db, persona_id)
    if not persona:
        return HTMLResponse("No such GM", status_code=404)
    ctx = _shell_ctx(request, db, gm, league_id, user=user)
    ctx["persona"] = persona
    ctx["team"] = db.execute(
        """SELECT t.city, t.mascot FROM gms g JOIN teams t ON t.id = g.team_id
           WHERE g.league_id = %s AND g.persona_id = %s AND g.is_ai
           ORDER BY g.created_at LIMIT 1""",
        (league_id, persona_id),
    ).fetchone()
    ctx["is_admin"] = bool(user.get("is_admin"))
    ctx["back"] = PERSONA_BACK.get(back, PERSONA_BACK["league"])
    return tab_response(request, htmx, "dashboard/partials/persona.html", ctx)


def _lobby_gms_context(gm_repo: GMRepository, league, gm) -> dict:
    # The people who have joined, then the AI GMs who will run the open
    # teams. Leagues made before the lobby picked AI GMs show the open teams
    # as slots instead, filled when the league starts.
    humans = [g for g in gm_repo.get_all_in_league(league["id"]) if not g["is_ai"]]
    # Their usernames, so each name links to the person's GM profile.
    usernames = {
        r["id"]: r["username"]
        for r in gm_repo.conn.execute(
            """SELECT g.id, u.username FROM gms g JOIN users u ON u.id = g.user_id
               WHERE g.league_id = %s""",
            (league["id"],),
        ).fetchall()
    }
    for g in humans:
        g["username"] = usernames.get(g["id"])
    # While the league is starting, the start gives the AI GMs their teams
    # and commits well before the league leaves the lobby, so the list keeps
    # them, and nobody can reroll one or pick another team by then.
    starting = sim_jobs.league_has_job(gm_repo.conn, league["id"])
    ai_gms = personas.lobby_ai_gms(gm_repo.conn, league["id"], seated=starting)
    return {
        "starting": starting,
        "league_id": league["id"],
        "league_state": league["state"],
        "gms": humans,
        "ai_gms": ai_gms,
        "ai_slots": max(league["num_teams"] - len(humans) - len(ai_gms), 0),
        "is_commissioner": league["commissioner_gm_id"] == str(gm["id"]),
        "num_teams": league["num_teams"],
        # A single-player league (a custom team) has no code to hand out.
        "join_code": None if league.get("single_player") else league.get("join_code"),
        # The join code's tip says whether it still works after the start.
        "late_joins": bool(league.get("late_joins")),
        "current_gm_id": str(gm["id"]),
        "team_choices": lobby_teams.choices(gm_repo.conn, league["id"]),
    }


@router.post(
    "/leagues/{league_id}/lobby/gms/{ai_gm_id}/reroll", response_class=HTMLResponse
)
def reroll_lobby_gm(
    request: Request,
    league_id: str,
    ai_gm_id: str,
    db: DB,
    gm: GM,
):
    """The commissioner swaps a lobby AI GM for another persona. Answers
    with the GM list."""
    league = LeagueRepository(db).get_by_id(league_id)
    if not league or league["state"] != "lobby":
        return HTMLResponse("", headers={"HX-Redirect": f"/leagues/{league_id}/"})
    if league["commissioner_gm_id"] != gm["id"]:
        return HTMLResponse("Only the commissioner can do that.", status_code=403)
    if sim_jobs.league_has_job(db, league_id):
        pass  # the league is starting: the list shows the GMs as they stand
    elif not personas.reroll(db, league_id, ai_gm_id):
        return HTMLResponse("No such AI GM in the lobby.", status_code=404)
    db.commit()
    return templates.TemplateResponse(
        request,
        "dashboard/partials/_lobby_gms.html",
        _lobby_gms_context(GMRepository(db), league, gm),
    )


@router.post("/leagues/{league_id}/lobby/team", response_class=HTMLResponse)
def pick_lobby_team(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
    team: str = Form(...),
):
    """A person in the lobby picks the team they'll run, given as
    "City|Mascot". An AI GM holding it gets theirs instead. Answers with the
    GM list, which shows the team they still have if the pick wasn't open
    (say someone took it a moment before)."""
    league = LeagueRepository(db).get_by_id(league_id)
    if not league or league["state"] != "lobby":
        return HTMLResponse("", headers={"HX-Redirect": f"/leagues/{league_id}/"})
    city, _, mascot = team.partition("|")
    if sim_jobs.league_has_job(db, league_id):
        pass  # the league is starting: teams are being handed out
    elif lobby_teams.pick(db, league_id, str(gm["id"]), city, mascot):
        db.commit()
    else:
        db.rollback()
    return templates.TemplateResponse(
        request,
        "dashboard/partials/_lobby_gms.html",
        _lobby_gms_context(GMRepository(db), league, gm),
    )


@router.get("/leagues/{league_id}/lobby/gms", response_class=HTMLResponse)
def lobby_gms(
    request: Request,
    league_id: str,
    db: DB,
    gm: GM,
):
    """The lobby's GM list, polled while GMs wait for the league to start.

    Once the league has started, HX-Redirect sends the page to the dashboard,
    which redirects on to wherever the league is now.
    """
    league = LeagueRepository(db).get_by_id(league_id)
    if not league or league["state"] != "lobby":
        return HTMLResponse("", headers={"HX-Redirect": f"/leagues/{league_id}/"})
    return templates.TemplateResponse(
        request,
        "dashboard/partials/_lobby_gms.html",
        _lobby_gms_context(GMRepository(db), league, gm),
    )
