# src/api/routers/leagues.py
#
# League list, creating and joining leagues, starting a league, renaming it,
# and the lobby page that /leagues/{id}/ shows before the league starts.

from __future__ import annotations

import random
import string
import uuid

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from src.api.dependencies import (
    DB,
    GM,
    ActiveLeague,
    Commissioner,
    GMOrViewer,
    IsHTMX,
    Unpaused,
    User,
)
from src.api.services import lobby_teams, personas, sim_jobs
from src.api.services.coach import coach_ctx
from src.api.services.leave_league import leave_league
from src.api.view_models.league_info import league_info
from src.api.view_models.welcome import welcome
from src.config import settings
from src.db.repositories.career_repo import CareerRepository
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.league_repo import LeagueRepository
from src.league import divisions
from src.league.league_modes import BLITZ, DEFAULT_MODE, SPEED_BLITZ, get_mode
from src.web.utils import _shell_ctx, tab_response, templates

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

    groups = {
        "tutorial": [lg for lg in mine if lg["is_practice"]],
        "running": [
            lg for lg in mine if not lg["is_practice"] and lg["state"] != "complete"
        ],
        "join": [lg for lg in public if lg["state"] == "lobby"],
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


def state_label(state: str, season_number: int) -> str:
    """The league's phase and which season it's in, e.g. "Draft 1" or
    "Playoffs 3". The lobby and a finished league have no season number."""
    if state in ("lobby", "complete") or not season_number:
        return state.title()
    return f"{state.title()} {season_number}"


@router.get("/leagues/new", response_class=HTMLResponse)
def new_league_page(request: Request):
    return templates.TemplateResponse(
        request,
        "leagues/new.html",
        {
            "default_mode": DEFAULT_MODE,
            "modes": [BLITZ, SPEED_BLITZ],
            "team_counts": divisions.TEAM_COUNTS,
            "default_team_count": divisions.DEFAULT_TEAM_COUNT,
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
    pace_control: str = Form("timer"),
    sim_period_days: int = Form(3),
    num_seasons: int = Form(10),
    is_public: bool = Form(False),
    trade_vote: bool = Form(False),
    pick_trades: bool = Form(False),
    injuries_enabled: bool | None = Form(None),
    num_teams: int = Form(divisions.DEFAULT_TEAM_COUNT),
    weighted_schedule: bool = Form(False),
):
    get_mode(mode)  # rejects an unknown mode
    if num_teams not in divisions.TEAM_COUNTS:
        raise ValueError(f"A league can't have {num_teams} teams.")
    if pace_control not in ("timer", "confirmed"):
        raise ValueError(f"Unknown pace '{pace_control}'.")
    if not 1 <= sim_period_days <= 30:
        raise ValueError("Days per sim period must be between 1 and 30.")
    if not 1 <= num_seasons <= 420:
        raise ValueError("Number of seasons must be between 1 and 420.")

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
            "pace_control": pace_control,
            "sim_period_days": sim_period_days,
            "num_seasons": num_seasons,
            "is_public": is_public,
            "trade_vote": trade_vote,
            "pick_trades": pick_trades,
            "num_teams": num_teams,
            "weighted_schedule": weighted_schedule,
            # Left out (an old form or a script), the mode's default.
            "injuries_enabled": (
                get_mode(mode).injuries_default
                if injuries_enabled is None
                else injuries_enabled
            ),
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

    if league["state"] != "lobby":
        return templates.TemplateResponse(
            request,
            "leagues/join.html",
            {
                "error": f"{league['name']} has already started, so it can't take new GMs.",
                "join_code": join_code,
            },
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
    if not league or not league["is_public"]:
        return RedirectResponse("/leagues/", status_code=302)

    gm_repo = GMRepository(db)
    if gm_repo.get_by_user_and_league(user["id"], league_id):
        return RedirectResponse(f"/leagues/{league_id}/", status_code=302)
    if league["state"] != "lobby":
        return RedirectResponse("/leagues/", status_code=302)

    gm_repo.create_gm(
        league_id=league_id,
        user_id=user["id"],
        display_name=user["display_name"],
    )
    personas.fill_lobby(db, league_id)  # they take an AI GM's place
    db.commit()
    return RedirectResponse(f"/leagues/{league_id}/", status_code=302)


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
    worker. The lobby polls the job, then opens the league."""
    job_id = sim_jobs.submit(db, league_id, "start")
    return JSONResponse(
        {"job_id": job_id, "poll": f"/leagues/{league_id}/jobs/{job_id}"},
        status_code=202,
    )


@router.post("/leagues/{league_id}/leave")
def leave_league_router(
    league_id: str,
    db: DB,
    gm: GM,
):
    """Leave the league. Once it has started, AI takes over the GM's team."""
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
):
    gm_repo = GMRepository(db)
    league_repo = LeagueRepository(db)
    league = league_repo.get_by_id(league_id)
    if not league:
        return RedirectResponse("/leagues/")

    # Viewers of a public league land on its standings, or its history once
    # it's over. The pages built around a GM's own team aren't open to them.
    if gm.get("is_viewer"):
        if league["state"] == "complete":
            return RedirectResponse(f"/leagues/{league_id}/history")
        return RedirectResponse(f"/leagues/{league_id}/standings")

    is_commish = league["commissioner_gm_id"] == gm["id"]

    state = league["state"]
    # Redirect logic
    if state in ("preseason", "draft"):
        # Once the draft is done, coming back in shows its results; the
        # board is only for a draft still to run.
        if league_repo.draft_complete(league_id):
            return RedirectResponse(f"/leagues/{league_id}/draft/results")
        # A GM's first look at a new league meets their team first.
        if league_repo.count_seasons(league_id) == 1 and gm_repo.needs_welcome(
            gm["id"]
        ):
            return RedirectResponse(f"/leagues/{league_id}/welcome")
        return RedirectResponse(f"/leagues/{league_id}/draft")
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
            "is_commissioner": bool(is_commish),
            "info": league_info(db, league),
            "coach": coach_ctx(db, league),
        }
    )

    return templates.TemplateResponse(
        request=request, name="dashboard/lobby.html", context=context
    )


@router.get("/leagues/{league_id}/league", response_class=HTMLResponse)
def league_page(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GMOrViewer,
):
    """The league's settings and who runs each team, for GMs and viewers once
    the league has started. The lobby shows the same before then."""
    league = LeagueRepository(db).get_by_id(league_id)
    if not league or league["state"] == "lobby":
        return RedirectResponse(f"/leagues/{league_id}/")
    ctx = _shell_ctx(request, db, gm, league_id, user=user)
    if not ctx["is_viewer"]:
        # The Leave League button warns the last person out that the league
        # goes with them.
        ctx["leaving_deletes_league"] = not GMRepository(db).has_people(
            league_id, besides_gm_id=gm["id"]
        )
    return tab_response(request, htmx, "dashboard/partials/league_info.html", ctx)


@router.get("/leagues/{league_id}/welcome", response_class=HTMLResponse)
def welcome_page(
    request: Request,
    htmx: IsHTMX,
    league_id: str,
    db: DB,
    user: User,
    gm: GM,
):
    """The GM's new team: shown once when the league starts, before the
    draft, and open from the Roster tab after."""
    league = LeagueRepository(db).get_by_id(league_id)
    if not league or league["state"] == "lobby":
        return RedirectResponse(f"/leagues/{league_id}/")
    team = welcome(db, league, gm)
    if not team:
        return RedirectResponse(f"/leagues/{league_id}/roster")
    GMRepository(db).mark_welcomed(gm["id"])
    ctx = _shell_ctx(request, db, gm, league_id, user=user)
    ctx["welcome"] = team
    return tab_response(request, htmx, "dashboard/partials/welcome.html", ctx)


# Pages that link to a persona card: the path it links back to, and its name.
PERSONA_BACK = {
    "league": ("league", "the League page"),
    "welcome": ("welcome", "your team"),
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
    ai_gms = personas.lobby_ai_gms(gm_repo.conn, league["id"])
    return {
        "league_id": league["id"],
        "league_state": league["state"],
        "gms": humans,
        "ai_gms": ai_gms,
        "ai_slots": max(league["num_teams"] - len(humans) - len(ai_gms), 0),
        "is_commissioner": league["commissioner_gm_id"] == str(gm["id"]),
        "num_teams": league["num_teams"],
        "join_code": league.get("join_code"),
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
    if not personas.reroll(db, league_id, ai_gm_id):
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
    if lobby_teams.pick(db, league_id, str(gm["id"]), city, mascot):
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
