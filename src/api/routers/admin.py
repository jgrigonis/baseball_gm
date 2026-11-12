# src/api/routers/admin.py
#
# The admin pages: every league with its settings and GMs, every user
# account, and the AI GM persona library. Only users with users.is_admin can
# open them (dependencies.Admin).
#
# Forms post back and redirect to the page they came from with ?done=<code>,
# which the page turns into a short note. A form that can't be saved renders
# the page again with the error.
#
# The work itself lives in src/api/services/admin.py.

from __future__ import annotations

import psycopg
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.api.dependencies import DB, Admin
from src.api.routers.leagues import state_label
from src.api.services import admin as admin_service
from src.api.services import badges, email_verify
from src.api.services.passwords import clean_email, password_error, username_error
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.league_repo import LeagueRepository
from src.api.services import owner_review
from src.api.services import owners as owner_service
from src.db.repositories.owner_repo import OwnerRepository
from src.db.repositories.persona_repo import PersonaRepository
from src.league import owners, personas
from src.db.repositories.user_repo import UserRepository
from src.league.league_constants import MAX_SEASONS, UNLIMITED_SEASONS
from src.league.league_modes import LEAGUE_MODES, injuries_allowed
from src.league.trade_deadline import trades_enabled_for
from src.player.contracts import format_salary
from src.web.utils import templates

router = APIRouter(prefix="/admin", tags=["admin"])

# What ?done=<code> says at the top of the page.
NOTES = {
    "settings": "Settings saved.",
    "paused": "League paused. It won't move on until you resume it.",
    "resumed": "League resumed.",
    "removed": "GM removed. If the league had started, AI runs their team now.",
    "league_deleted": "That was the last person in the league, so it was deleted.",
    "created": "User added.",
    "email": "Email saved.",
    "password": "Password set. They've been signed out everywhere.",
    "admin_on": "They're an admin now.",
    "admin_off": "They're no longer an admin.",
    "contributor_on": "They're a paid contributor now, with the badge on their profile.",
    "contributor_off": "They're no longer a paid contributor.",
    "user_deleted": "User deleted.",
    "persona_created": "Persona created.",
    "chance": "Chance saved.",
    "persona_deleted": "Persona deleted.",
    "owner_created": "Owner created.",
    "owner_deleted": "Owner deleted.",
}


def _done(url: str, code: str) -> RedirectResponse:
    return RedirectResponse(f"{url}?done={code}", status_code=303)


def _page(request: Request, name: str, ctx: dict, status_code: int = 200):
    ctx["note"] = NOTES.get(request.query_params.get("done", ""))
    return templates.TemplateResponse(
        request, f"admin/{name}", ctx, status_code=status_code
    )


@router.get("/")
def admin_home(_: Admin):
    return RedirectResponse("/admin/leagues", status_code=302)


# ── Leagues ───────────────────────────────────────────────────────────────────


@router.get("/leagues", response_class=HTMLResponse)
def leagues(request: Request, db: DB, user: Admin):
    rows = LeagueRepository(db).list_for_admin()
    for league in rows:
        league["state_label"] = state_label(league["state"], league["season_number"])
    return _page(request, "leagues.html", {"user": user, "leagues": rows})


def _league_or_404(db, league_id: str) -> dict:
    league = LeagueRepository(db).get_by_id(league_id)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    return league


def _league_page(request, db, user, league_id: str, status_code=200, **ctx):
    league_repo = LeagueRepository(db)
    league = _league_or_404(db, league_id)
    season_number = league_repo.count_seasons(league_id)
    gms = db.execute(
        """SELECT g.*, u.username, t.city, t.mascot
           FROM gms g
           LEFT JOIN users u ON u.id = g.user_id
           LEFT JOIN teams t ON t.id = g.team_id
           WHERE g.league_id = %s
           ORDER BY g.is_ai, g.created_at""",
        (league_id,),
    ).fetchall()
    return _page(
        request,
        "league.html",
        {
            "user": user,
            "league": league,
            "state_label": state_label(league["state"], season_number),
            "season_number": season_number,
            "gms": [dict(g) for g in gms],
            "modes": [LEAGUE_MODES[k] for k in admin_service.MODES],
            "ranges": admin_service.NUMBER_RANGES,
            "admin_windows": admin_service.ADMIN_WINDOW_RANGE,
            "season_choices": _season_choices(league["num_seasons"]),
            # Leagues made before these settings go by their mode's default.
            "injuries_on": injuries_allowed(league),
            "trades_on": trades_enabled_for(league),
            "owners": _league_owners(db, league),
            "owner_cap": _league_cap(db, league),
            **ctx,
        },
        status_code,
    )


def _league_cap(db, league) -> str | None:
    """The league's payroll cap this season, for the owners table."""
    year = ContractRepository(db).current_year(league["id"])
    if year is None:
        return None
    caps = {
        m.get("cap") for m in BudgetRepository(db).finances(league["id"], year).values()
    }
    cap = next(iter(caps - {None}), None)
    return _money(cap) if cap else None


def _league_owners(db, league: dict) -> list[dict]:
    """Each team's owner, with the numbers players never see."""
    if league["state"] == "lobby":
        return []
    by_team = owner_service.ensure(db, league["id"])
    db.commit()
    names = {
        r["id"]: f"{r['city']} {r['mascot']}"
        for r in db.execute(
            "SELECT id, city, mascot FROM teams WHERE id = ANY(%s)",
            (list(by_team),),
        ).fetchall()
    }
    budgets = BudgetRepository(db)
    year = ContractRepository(db).current_year(league["id"])
    now = budgets.finances(league["id"], year) if year else {}
    last = budgets.finances(league["id"], year - 1) if year else {}
    reviews = owner_review.security_now(db, league["id"])
    rows = []
    for team_id, o in by_team.items():
        traits = owners.clean_traits(o["traits"])
        money = now.get(team_id, {})
        review = reviews.get(team_id)
        done = money if money.get("profit") is not None else last.get(team_id, {})
        rows.append(
            {
                "team": names.get(team_id, team_id),
                "owner_id": o["owner_id"],
                "name": o["name"],
                "archetype": o["archetype"],
                "rival": names.get(o["rival_team_id"]) if o["rival_team_id"] else None,
                "since_year": o["since_year"],
                "top": [
                    dict(k=k, label=label)
                    for k, label, _ in owners.DIMENSIONS
                    if k in owners.top_dimensions(o["weights"])
                ],
                "patience": traits["patience"],
                "spending": traits["spending"],
                "budget": _money(money.get("budget")),
                "revenue": _money(money.get("revenue")),
                "fans": money.get("fans_before"),
                "profit": _money(done.get("profit")),
                "profit_year": year if done is money else (year or 1) - 1,
                "review": _review_row(review),
            }
        )
    return sorted(rows, key=lambda r: r["team"])


def _review_row(review: dict | None) -> dict | None:
    """An owner's latest season review for the admin scorecard."""
    if not review:
        return None
    detail = review["detail"] or {}
    scores = detail.get("scores", {})
    return {
        "year": review["year"],
        "score": review["score"],
        "security": review["job_security"],
        "before": detail.get("security_before"),
        # Fired, or past the line but held back (firing off in the league,
        # or the owner's honeymoon or warning first).
        "verdict": (
            "fired"
            if review["verdict"] == "fired"
            else "would fire"
            if detail.get("would_fire")
            else review["verdict"]
        ),
        "dimensions": [
            {"label": label, "score": scores.get(k)}
            for k, label, _ in owners.DIMENSIONS
        ],
        "win_target": detail.get("win_target"),
    }


def _money(amount) -> str | None:
    if amount is None:
        return None
    return ("-" if amount < 0 else "") + format_salary(abs(amount))


def _season_choices(current: int) -> list[int]:
    """The seasons slider's stops, as on the New League form: 1..MAX_SEASONS,
    then unlimited (0). A league already past MAX_SEASONS keeps its count."""
    choices = [*range(1, MAX_SEASONS + 1), UNLIMITED_SEASONS]
    if current not in choices:
        choices.insert(-1, current)
    return choices


@router.get("/leagues/{league_id}", response_class=HTMLResponse)
def league_detail(request: Request, league_id: str, db: DB, user: Admin):
    return _league_page(request, db, user, league_id)


@router.post("/leagues/{league_id}/settings")
def league_settings(
    request: Request,
    league_id: str,
    db: DB,
    user: Admin,
    name: str = Form(...),
    mode: str = Form(...),
    pace_control: str = Form(...),
    decision_window_sec: int = Form(...),
    draft_window_sec: int = Form(...),
    lineup_window_sec: int = Form(...),
    sim_period_days: int = Form(...),
    num_seasons: int = Form(...),
    backstory_years: int | None = Form(None),
    reentry_enabled: bool = Form(False),
    owner_firing: bool = Form(False),
    is_public: bool = Form(False),
    late_joins: bool = Form(False),
    injuries_enabled: bool = Form(False),
    trades_enabled: bool = Form(False),
    pick_trades: bool = Form(False),
    weighted_schedule: bool = Form(False),
    commissioner_gm_id: str = Form(""),
):
    league = _league_or_404(db, league_id)
    if backstory_years is None:
        backstory_years = league["backstory_years"]
    error = admin_service.update_league_settings(
        db,
        league_id,
        {
            "name": name,
            "mode": mode,
            "pace_control": pace_control,
            "decision_window_sec": decision_window_sec,
            "draft_window_sec": draft_window_sec,
            "lineup_window_sec": lineup_window_sec,
            "sim_period_days": sim_period_days,
            "num_seasons": num_seasons,
            "backstory_years": backstory_years,
            "reentry_enabled": reentry_enabled,
            "owner_firing": owner_firing,
            "is_public": is_public,
            "late_joins": late_joins,
            "injuries_enabled": injuries_enabled,
            "trades_enabled": trades_enabled,
            "pick_trades": pick_trades,
            "weighted_schedule": weighted_schedule,
            "commissioner_gm_id": commissioner_gm_id or None,
        },
    )
    if error:
        return _league_page(request, db, user, league_id, 400, error=error)
    return _done(f"/admin/leagues/{league_id}", "settings")


@router.post("/leagues/{league_id}/pause")
def pause_league(league_id: str, db: DB, _: Admin):
    _league_or_404(db, league_id)
    admin_service.set_paused(db, league_id, True)
    return _done(f"/admin/leagues/{league_id}", "paused")


@router.post("/leagues/{league_id}/resume")
def resume_league(league_id: str, db: DB, _: Admin):
    _league_or_404(db, league_id)
    admin_service.set_paused(db, league_id, False)
    return _done(f"/admin/leagues/{league_id}", "resumed")


@router.post("/leagues/{league_id}/gms/{gm_id}/remove")
def remove_gm(league_id: str, gm_id: str, db: DB, _: Admin):
    _league_or_404(db, league_id)
    admin_service.remove_gm(db, league_id, gm_id)
    if not LeagueRepository(db).get_by_id(league_id):
        return _done("/admin/leagues", "league_deleted")
    return _done(f"/admin/leagues/{league_id}", "removed")


# ── Users ─────────────────────────────────────────────────────────────────────


def _users_page(request, db, user, status_code=200, **ctx):
    return _page(
        request,
        "users.html",
        {"user": user, "users": UserRepository(db).list_all(), **ctx},
        status_code,
    )


@router.get("/users", response_class=HTMLResponse)
def users(request: Request, db: DB, user: Admin):
    return _users_page(request, db, user)


@router.post("/users")
def add_user(
    request: Request,
    db: DB,
    user: Admin,
    username: str = Form(...),
    password: str = Form(...),
    email: str = Form(""),
    is_admin: bool = Form(False),
    must_change: bool = Form(False),
):
    username = username.strip()
    user_repo = UserRepository(db)
    clean, error = clean_email(email)
    error = username_error(username) or password_error(password, password) or error
    if not error and user_repo.username_taken(username):
        error = "That username is taken."
    if not error and clean and user_repo.email_taken(clean):
        error = "Another user has that email."
    if not error:
        try:
            admin_service.create_user(
                db, username, password, clean, is_admin, must_change
            )
        except psycopg.errors.UniqueViolation:
            db.rollback()
            error = "That username or email is taken."
    if error:
        form = {"username": username, "email": email, "is_admin": is_admin}
        return _users_page(request, db, user, 400, error=error, form=form)
    return _done("/admin/users", "created")


def _user_or_404(db, user_id: str) -> dict:
    row = UserRepository(db).get_by_id(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row


def _user_page(request, db, admin, user_id: str, status_code=200, **ctx):
    return _page(
        request,
        "user.html",
        {
            "user": admin,
            "account": _user_or_404(db, user_id),
            "leagues": admin_service.user_leagues(db, user_id),
            "is_self": admin["id"] == user_id,
            **ctx,
        },
        status_code,
    )


@router.get("/users/{user_id}", response_class=HTMLResponse)
def user_detail(request: Request, user_id: str, db: DB, user: Admin):
    return _user_page(request, db, user, user_id)


@router.post("/users/{user_id}/email")
def set_email(
    request: Request, user_id: str, db: DB, user: Admin, email: str = Form("")
):
    _user_or_404(db, user_id)
    clean, error = clean_email(email)
    if not error and clean and UserRepository(db).email_taken(clean, user_id):
        error = "Another user has that email."
    if error:
        return _user_page(
            request, db, user, user_id, 400, email_error=error, email=email
        )
    if UserRepository(db).set_email(user_id, clean):
        email_verify.email_changed(db, user_id)
    badges.award(db, user_id)  # Email on File
    db.commit()
    return _done(f"/admin/users/{user_id}", "email")


@router.post("/users/{user_id}/password")
def set_password(
    request: Request,
    user_id: str,
    db: DB,
    user: Admin,
    password: str = Form(...),
    confirm: str = Form(...),
    must_change: bool = Form(False),
):
    _user_or_404(db, user_id)
    error = password_error(password, confirm)
    if error:
        return _user_page(request, db, user, user_id, 400, password_error=error)
    admin_service.set_password(db, user_id, password, must_change)
    if user_id == user["id"]:
        # Their own session was just replaced too; sign them in again.
        return RedirectResponse("/", status_code=303)
    return _done(f"/admin/users/{user_id}", "password")


@router.post("/users/{user_id}/admin")
def set_admin(
    request: Request,
    user_id: str,
    db: DB,
    user: Admin,
    is_admin: bool = Form(False),
):
    account = _user_or_404(db, user_id)
    if not is_admin and user_id == user["id"]:
        return _user_page(
            request,
            db,
            user,
            user_id,
            400,
            admin_error="You can't take away your own admin access.",
        )
    if not account["has_password"]:
        return _user_page(
            request,
            db,
            user,
            user_id,
            400,
            admin_error="Only an account with a password can be an admin.",
        )
    UserRepository(db).set_admin(user_id, is_admin)
    db.commit()
    return _done(f"/admin/users/{user_id}", "admin_on" if is_admin else "admin_off")


@router.post("/users/{user_id}/contributor")
def set_contributor(
    user_id: str,
    db: DB,
    user: Admin,
    is_contributor: bool = Form(False),
):
    """Paid contributor, set by hand until there are payments."""
    _user_or_404(db, user_id)
    UserRepository(db).set_contributor(user_id, is_contributor)
    if is_contributor:
        badges.award(db, user_id)
    else:
        badges.take_back(db, user_id, "contributor")
    db.commit()
    code = "contributor_on" if is_contributor else "contributor_off"
    return _done(f"/admin/users/{user_id}", code)


@router.post("/users/{user_id}/delete")
def delete_user(request: Request, user_id: str, db: DB, user: Admin):
    _user_or_404(db, user_id)
    if user_id == user["id"]:
        return _user_page(
            request,
            db,
            user,
            user_id,
            400,
            delete_error="You can't delete your own account.",
        )
    admin_service.delete_user(db, user_id)
    return _done("/admin/users", "user_deleted")


# ── Personas ──────────────────────────────────────────────────────────────────
# Created once and never edited (src/league/personas.py); only the chance of
# being picked for a new league changes. Duplicate pre-fills the create form.


def _personas_page(request, db, user, status_code=200, **ctx):
    rows = PersonaRepository(db).all()
    form = ctx.pop("form", None)
    source = request.query_params.get("from")
    if form is None and source:
        p = PersonaRepository(db).get(source)
        if p:
            form = {
                "name": "",
                "bio": p["bio"],
                "archetype": p["archetype"],
                "dials": personas.clean(p["dials"]),
                "chance": p["chance"],
                "from_name": p["name"],
            }
    form = form or {
        "dials": dict(personas.NEUTRAL),
        "chance": personas.DEFAULT_CHANCE,
    }
    return _page(
        request,
        "personas.html",
        {
            "user": user,
            "personas": rows,
            "archetypes": sorted({r["archetype"] for r in rows if r["archetype"]}),
            "traits": personas.TRAITS,
            "form": form,
            **ctx,
        },
        status_code,
    )


@router.get("/personas", response_class=HTMLResponse)
def persona_list(request: Request, db: DB, user: Admin):
    return _personas_page(request, db, user)


@router.post("/personas")
async def create_persona(request: Request, db: DB, user: Admin):
    data = await request.form()
    name = " ".join(str(data.get("name", "")).split())
    bio = str(data.get("bio", "")).strip()
    archetype = " ".join(str(data.get("archetype", "")).split())
    dials = personas.clean({k: data.get(k) for k in personas.DIALS})
    chance = _chance(data.get("chance"))
    form = {
        "name": name,
        "bio": bio,
        "archetype": archetype,
        "dials": dials,
        "chance": personas.DEFAULT_CHANCE if chance is None else chance,
    }
    repo = PersonaRepository(db)
    error = None
    if not 2 <= len(name) <= 60:
        error = "A persona needs a name of 2 to 60 characters."
    elif len(bio) > 200 or len(archetype) > 60:
        error = "Keep the bio under 200 characters and the archetype under 60."
    elif chance is None:
        error = "Chance is a whole number from 0 to 100."
    elif repo.name_taken(name):
        error = "There's already a persona with that name."
    if error:
        return _personas_page(request, db, user, 400, error=error, form=form)
    persona_id = repo.create(name, bio, archetype, dials, chance)
    db.commit()
    return _done(f"/admin/personas/{persona_id}", "persona_created")


def _chance(value) -> int | None:
    try:
        chance = int(str(value).strip())
    except TypeError, ValueError:
        return None
    return chance if 0 <= chance <= personas.MAX_CHANCE else None


def _persona_or_404(db, persona_id: str) -> dict:
    p = PersonaRepository(db).get(persona_id)
    if not p:
        raise HTTPException(status_code=404, detail="Persona not found")
    return p


def _persona_page(request, db, user, persona_id: str, status_code=200, **ctx):
    p = _persona_or_404(db, persona_id)
    repo = PersonaRepository(db)
    return _page(
        request,
        "persona.html",
        {
            "user": user,
            "persona": p,
            "traits": personas.describe(p["dials"]),
            "profile": personas.profile(p["dials"]),
            "leagues": repo.leagues_using(persona_id),
            **ctx,
        },
        status_code,
    )


@router.get("/personas/{persona_id}", response_class=HTMLResponse)
def persona_detail(request: Request, persona_id: str, db: DB, user: Admin):
    return _persona_page(request, db, user, persona_id)


@router.post("/personas/{persona_id}/chance")
def persona_chance(
    request: Request, persona_id: str, db: DB, user: Admin, chance: str = Form(...)
):
    _persona_or_404(db, persona_id)
    value = _chance(chance)
    if value is None:
        return _persona_page(
            request,
            db,
            user,
            persona_id,
            400,
            error="Chance is a whole number from 0 to 100.",
        )
    PersonaRepository(db).set_chance(persona_id, value)
    db.commit()
    return _done(f"/admin/personas/{persona_id}", "chance")


@router.post("/personas/{persona_id}/delete")
def persona_delete(request: Request, persona_id: str, db: DB, user: Admin):
    _persona_or_404(db, persona_id)
    if not PersonaRepository(db).delete(persona_id):
        return _persona_page(
            request,
            db,
            user,
            persona_id,
            400,
            error="This persona is in a league, so it can't be deleted. "
            "Set its chance to 0 to keep new leagues from picking it.",
        )
    db.commit()
    return _done("/admin/personas", "persona_deleted")


# ── Owners ────────────────────────────────────────────────────────────────────
# The team owner library (src/league/owners.py), run like the personas: an
# owner is created once and never edited; only the chance of being drawn for
# a team changes. Duplicate pre-fills the create form.


def _owners_page(request, db, user, status_code=200, **ctx):
    repo = OwnerRepository(db)
    rows = repo.all()
    form = ctx.pop("form", None)
    source = request.query_params.get("from")
    if form is None and source:
        o = repo.get(source)
        if o:
            form = {
                "name": "",
                "bio": o["bio"],
                "archetype": o["archetype"],
                "weights": owners.clean_weights(o["weights"]),
                "traits": owners.clean_traits(o["traits"]),
                "chance": o["chance"],
                "from_name": o["name"],
            }
    form = form or {
        "weights": owners.clean_weights({}),
        "traits": owners.clean_traits({}),
        "chance": owners.DEFAULT_CHANCE,
    }
    for r in rows:
        r["traits"] = owners.clean_traits(r["traits"])
        r["top"] = [
            label
            for k, label, _ in owners.DIMENSIONS
            if k in owners.top_dimensions(r["weights"], 2)
        ]
    return _page(
        request,
        "owners.html",
        {
            "user": user,
            "owners": rows,
            "archetypes": sorted({r["archetype"] for r in rows if r["archetype"]}),
            "dimensions": owners.DIMENSIONS,
            "traits": owners.TRAITS,
            "form": form,
            **ctx,
        },
        status_code,
    )


@router.get("/owners", response_class=HTMLResponse)
def owner_list(request: Request, db: DB, user: Admin):
    return _owners_page(request, db, user)


@router.post("/owners")
async def create_owner(request: Request, db: DB, user: Admin):
    data = await request.form()
    name = " ".join(str(data.get("name", "")).split())
    bio = str(data.get("bio", "")).strip()
    archetype = " ".join(str(data.get("archetype", "")).split())
    weights = owners.clean_weights({k: data.get(f"w_{k}") for k in owners.WEIGHTS})
    traits = owners.clean_traits({k: data.get(f"t_{k}") for k in owners.TRAIT_KEYS})
    chance = _chance(data.get("chance"))
    form = {
        "name": name,
        "bio": bio,
        "archetype": archetype,
        "weights": weights,
        "traits": traits,
        "chance": owners.DEFAULT_CHANCE if chance is None else chance,
    }
    repo = OwnerRepository(db)
    error = None
    if not 2 <= len(name) <= 60:
        error = "An owner needs a name of 2 to 60 characters."
    elif len(bio) > 200 or len(archetype) > 60:
        error = "Keep the bio under 200 characters and the archetype under 60."
    elif chance is None:
        error = "Chance is a whole number from 0 to 100."
    elif not any(weights.values()):
        error = "An owner has to care about something: give a weight above 0."
    elif repo.name_taken(name):
        error = "There's already an owner with that name."
    if error:
        return _owners_page(request, db, user, 400, error=error, form=form)
    owner_id = repo.create(name, bio, archetype, weights, traits, chance)
    db.commit()
    return _done(f"/admin/owners/{owner_id}", "owner_created")


def _owner_or_404(db, owner_id: str) -> dict:
    o = OwnerRepository(db).get(owner_id)
    if not o:
        raise HTTPException(status_code=404, detail="Owner not found")
    return o


def _owner_page(request, db, user, owner_id: str, status_code=200, **ctx):
    o = _owner_or_404(db, owner_id)
    weights = owners.clean_weights(o["weights"])
    traits = owners.clean_traits(o["traits"])
    total = sum(weights.values()) or 1
    return _page(
        request,
        "owner.html",
        {
            "user": user,
            "owner": o,
            "wants": owners.wants(o["archetype"]),
            "weights": [
                {
                    "label": label,
                    "how": how,
                    "value": weights[k],
                    "share": round(100 * weights[k] / total),
                }
                for k, label, how in owners.DIMENSIONS
            ],
            "traits": [
                {"label": label, "ends": (low, high), "value": traits[k]}
                for k, label, low, high in owners.TRAITS
            ],
            "leagues": OwnerRepository(db).leagues_using(owner_id),
            **ctx,
        },
        status_code,
    )


@router.get("/owners/{owner_id}", response_class=HTMLResponse)
def owner_detail(request: Request, owner_id: str, db: DB, user: Admin):
    return _owner_page(request, db, user, owner_id)


@router.post("/owners/{owner_id}/chance")
def owner_chance(
    request: Request, owner_id: str, db: DB, user: Admin, chance: str = Form(...)
):
    _owner_or_404(db, owner_id)
    value = _chance(chance)
    if value is None:
        return _owner_page(
            request,
            db,
            user,
            owner_id,
            400,
            error="Chance is a whole number from 0 to 100.",
        )
    OwnerRepository(db).set_chance(owner_id, value)
    db.commit()
    return _done(f"/admin/owners/{owner_id}", "chance")


@router.post("/owners/{owner_id}/delete")
def owner_delete(request: Request, owner_id: str, db: DB, user: Admin):
    _owner_or_404(db, owner_id)
    if not OwnerRepository(db).delete(owner_id):
        return _owner_page(
            request,
            db,
            user,
            owner_id,
            400,
            error="This owner is in a league, so they can't be deleted. "
            "Set their chance to 0 to keep new teams from drawing them.",
        )
    db.commit()
    return _done("/admin/owners", "owner_deleted")
