# src/api/routers/auth.py
#
# Landing page, accounts, and sign in / sign out.
#
# Identity model (matches schema.py):
#   users.username + users.password_hash  ← what a person signs in with
#   users.session_token                   ← stored in "gm_session" browser cookie
#   users → gms                           via gms.user_id (one gm row per league)
#
# So the resolution chain is:
#   cookie → users row → gms row WHERE league_id = ?
#
# Signing in hands the browser the user's current session_token, so several
# browsers can be signed in at once; signing out replaces the token, which
# signs out every browser.
#
# Guests created before passwords existed have a session cookie but no
# username or password. /leagues/ sends them to /auth/set-password, which
# gives them a login and a fresh token so any old copy of the guest cookie
# stops working.
#
# Account creation only makes a users row. The gms row is created when the
# user creates or joins a league (see leagues.py).

from __future__ import annotations

import uuid

import psycopg
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.api.dependencies import DB, OptionalUser, User
from src.api.services.passwords import (
    hash_password,
    needs_rehash,
    password_error,
    username_error,
    verify_password,
)
from src.db.repositories.user_repo import UserRepository
from src.web.utils import templates

router = APIRouter(tags=["web"])

SESSION_COOKIE = "gm_session"


def _new_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex


def _signed_in(token: str) -> RedirectResponse:
    resp = RedirectResponse("/leagues/", status_code=302)
    resp.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=60 * 60 * 24 * 365 * 5,
        httponly=True,
        samesite="lax",
    )
    return resp


def _landing(request: Request, status_code: int = 200, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "landing.html", ctx, status_code=status_code
    )


@router.get("/", response_class=HTMLResponse)
def landing(request: Request, user: OptionalUser):
    if user:
        return RedirectResponse("/leagues/")
    return _landing(request)


@router.post("/auth/register")
def register(
    request: Request,
    db: DB,
    username: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
):
    username = username.strip()
    error = username_error(username) or password_error(password, confirm)
    user_repo = UserRepository(db)
    if not error and user_repo.username_taken(username):
        error = "That username is taken."
    if error:
        return _landing(request, 400, register_error=error, register_username=username)

    token = _new_token()
    try:
        user_repo.insert_user(
            str(uuid.uuid4()), token, username, username, hash_password(password)
        )
        db.commit()
    except psycopg.errors.UniqueViolation:
        # Someone took the name between the check and the insert.
        db.rollback()
        return _landing(
            request,
            400,
            register_error="That username is taken.",
            register_username=username,
        )
    return _signed_in(token)


@router.post("/auth/login")
def login(
    request: Request,
    db: DB,
    username: str = Form(...),
    password: str = Form(...),
):
    username = username.strip()
    user_repo = UserRepository(db)
    row = user_repo.get_login(username)
    if not verify_password(row["password_hash"] if row else None, password):
        return _landing(
            request,
            401,
            login_error="Wrong username or password.",
            login_username=username,
        )

    if needs_rehash(row["password_hash"]):
        user_repo.set_password_hash(row["id"], hash_password(password))
        db.commit()
    return _signed_in(row["session_token"])


@router.get("/auth/set-password", response_class=HTMLResponse)
def set_password_page(request: Request, user: User):
    if user["has_password"]:
        return RedirectResponse("/leagues/", status_code=302)
    return templates.TemplateResponse(
        request,
        "set_password.html",
        {"username": user["display_name"]},
    )


@router.post("/auth/set-password")
def set_password(
    request: Request,
    db: DB,
    user: User,
    username: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
):
    """Give a legacy passwordless guest a username and password."""
    if user["has_password"]:
        return RedirectResponse("/leagues/", status_code=302)

    username = username.strip()
    error = username_error(username) or password_error(password, confirm)
    user_repo = UserRepository(db)
    if not error and user_repo.username_taken(username):
        error = "That username is taken."

    token = _new_token()
    if not error:
        try:
            user_repo.set_credentials(
                user["id"], username, hash_password(password), token
            )
            db.commit()
        except psycopg.errors.UniqueViolation:
            db.rollback()
            error = "That username is taken."

    if error:
        return templates.TemplateResponse(
            request,
            "set_password.html",
            {"username": username, "error": error},
            status_code=400,
        )
    return _signed_in(token)


@router.post("/auth/logout")
def logout(db: DB, user: OptionalUser):
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie(SESSION_COOKIE, httponly=True, samesite="lax")

    if user:
        UserRepository(db).invalidate_session(user["id"])
        db.commit()
    return resp
