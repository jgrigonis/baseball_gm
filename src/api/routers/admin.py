# src/api/routers/admin.py
#
# The admin pages: every league with its settings and GMs, and every user
# account. Only users with users.is_admin can open them (dependencies.Admin).
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
from src.api.services.passwords import password_error, username_error
from src.db.repositories.league_repo import LeagueRepository
from src.db.repositories.user_repo import UserRepository
from src.league.league_modes import LEAGUE_MODES
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
    "user_deleted": "User deleted.",
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
            **ctx,
        },
        status_code,
    )


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
    reentry_enabled: bool = Form(False),
    is_public: bool = Form(False),
    commissioner_gm_id: str = Form(""),
):
    _league_or_404(db, league_id)
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
            "reentry_enabled": reentry_enabled,
            "is_public": is_public,
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
    clean, error = admin_service.clean_email(email)
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
    clean, error = admin_service.clean_email(email)
    if not error and clean and UserRepository(db).email_taken(clean, user_id):
        error = "Another user has that email."
    if error:
        return _user_page(
            request, db, user, user_id, 400, email_error=error, email=email
        )
    UserRepository(db).set_email(user_id, clean)
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
