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
#
# Too many wrong passwords for one username, or from one IP, and sign-in is
# refused for a while (services/login_limits.py).
#
# A forgotten password is reset through an emailed link (/auth/forgot, then
# /auth/reset; see services/password_reset.py). /account is where a user adds
# or changes the email those links go to.

from __future__ import annotations

import uuid

import psycopg
from fastapi import APIRouter, BackgroundTasks, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.api.dependencies import DB, OptionalUser, User
from src.api.services import badges, login_limits, mailer, password_reset
from src.api.services.passwords import (
    clean_email,
    hash_password,
    needs_rehash,
    password_error,
    username_error,
    verify_password,
)
from src.config import settings
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
        secure=settings.served_over_https,
    )
    return resp


def _landing(request: Request, status_code: int = 200, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "landing.html", ctx, status_code=status_code
    )


def _signup(request: Request, status_code: int = 200, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "signup.html", ctx, status_code=status_code
    )


@router.get("/", response_class=HTMLResponse)
def landing(request: Request, user: OptionalUser):
    if user:
        return RedirectResponse("/leagues/")
    return _landing(request)


@router.get("/signup", response_class=HTMLResponse)
def signup_page(request: Request, user: OptionalUser):
    if user:
        return RedirectResponse("/leagues/")
    return _signup(request)


@router.post("/auth/register")
def register(
    request: Request,
    db: DB,
    username: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
    email: str = Form(""),
):
    username = username.strip()
    clean, email_error = clean_email(email)
    error = username_error(username) or email_error or password_error(password, confirm)
    user_repo = UserRepository(db)
    if not error and user_repo.username_taken(username):
        error = "That username is taken."
    if not error and clean and user_repo.email_taken(clean):
        error = "Another account has that email."
    if error:
        return _signup(request, 400, error=error, username=username, email=email)

    token = _new_token()
    try:
        user_repo.insert_user(
            str(uuid.uuid4()),
            token,
            username,
            username,
            hash_password(password),
            email=clean,
        )
        db.commit()
    except psycopg.errors.UniqueViolation:
        # Someone took the name or email between the check and the insert.
        db.rollback()
        return _signup(
            request,
            400,
            error="That username or email is taken.",
            username=username,
            email=email,
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
    ip = login_limits.client_ip(request)
    # Checked before the password, so a blocked guess costs no hashing.
    wait = login_limits.minutes_blocked(db, username, ip)
    if wait:
        return _landing(
            request,
            429,
            error=(
                f"Too many sign-in attempts. Try again in {wait} "
                f"minute{'s' if wait != 1 else ''}, or reset your password."
            ),
            username=username,
        )

    user_repo = UserRepository(db)
    row = user_repo.get_login(username)
    if not verify_password(row["password_hash"] if row else None, password):
        login_limits.record_failure(db, username, ip)
        db.commit()
        return _landing(
            request,
            401,
            error="Wrong username or password.",
            username=username,
        )

    if needs_rehash(row["password_hash"]):
        user_repo.set_password_hash(row["id"], hash_password(password))
    login_limits.clear(db, username)
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
    resp.delete_cookie(
        SESSION_COOKIE,
        httponly=True,
        samesite="lax",
        secure=settings.served_over_https,
    )

    if user:
        UserRepository(db).invalidate_session(user["id"])
        db.commit()
    return resp


# ── Changing a password ───────────────────────────────────────────────────────
#
# Required before anything else for the default admin and for anyone whose
# password an admin set (users.must_change_password, see dependencies.py).


def _change_password_page(request: Request, user, status_code: int = 200, **ctx):
    return templates.TemplateResponse(
        request,
        "change_password.html",
        {"forced": user["must_change_password"], "username": user["username"], **ctx},
        status_code=status_code,
    )


@router.get("/auth/change-password", response_class=HTMLResponse)
def change_password_page(request: Request, user: User):
    if not user["has_password"]:
        return RedirectResponse("/auth/set-password", status_code=302)
    return _change_password_page(request, user)


@router.post("/auth/change-password")
def change_password(
    request: Request,
    db: DB,
    user: User,
    current: str = Form(...),
    password: str = Form(...),
    confirm: str = Form(...),
):
    user_repo = UserRepository(db)
    row = user_repo.get_login(user["username"] or "")
    error = None
    if not verify_password(row["password_hash"] if row else None, current):
        error = "Your current password is wrong."
    else:
        error = password_error(password, confirm)
    if not error and password == current:
        error = "Choose a password different from the current one."
    if error:
        return _change_password_page(request, user, 400, error=error)

    token = _new_token()
    user_repo.set_password(
        user["id"], hash_password(password), token, must_change=False
    )
    db.commit()
    return _signed_in(token)


# ── Forgotten passwords ───────────────────────────────────────────────────────
#
# Every request gets the same answer, whether or not the account exists or has
# an email, so the page can't be used to find out who has an account. The
# email goes out after the response, so timing doesn't tell either. That
# includes requests over the per-account or per-IP limits: they get the same
# page and no email.


def _forgot_page(request: Request, status_code: int = 200, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "forgot_password.html",
        {"ttl_minutes": password_reset.RESET_TTL_MINUTES, **ctx},
        status_code=status_code,
    )


@router.get("/auth/forgot", response_class=HTMLResponse)
def forgot_page(request: Request):
    return _forgot_page(request)


@router.post("/auth/forgot")
def forgot(
    request: Request,
    db: DB,
    background_tasks: BackgroundTasks,
    login: str = Form(...),
):
    email = password_reset.request_reset(
        db,
        login,
        login_limits.client_ip(request),
        str(request.base_url),
    )
    if email:
        background_tasks.add_task(mailer.send, email.to, email.subject, email.text)
    return _forgot_page(request, sent=True)


def _reset_page(request: Request, status_code: int = 200, **ctx) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "reset_password.html", ctx, status_code=status_code
    )


@router.get("/auth/reset", response_class=HTMLResponse)
def reset_page(request: Request, db: DB, token: str = ""):
    # Opening the link doesn't use it up: some mail scanners open links
    # before the person does. Only the form below spends it.
    account = password_reset.account_for_token(db, token)
    if not account:
        return _reset_page(request, 400, expired=True)
    return _reset_page(request, token=token, username=account["username"])


@router.post("/auth/reset")
def reset(
    request: Request,
    db: DB,
    token: str = Form(""),
    password: str = Form(...),
    confirm: str = Form(...),
):
    account = password_reset.account_for_token(db, token)
    if not account:
        return _reset_page(request, 400, expired=True)
    # Check the new password before spending the link, so a typo doesn't
    # mean asking for another email.
    error = password_error(password, confirm)
    if error:
        return _reset_page(
            request, 400, token=token, username=account["username"], error=error
        )

    user_id = password_reset.use_token(db, token)
    if not user_id:
        # Used by another tab or expired in the last moment.
        return _reset_page(request, 400, expired=True)
    session = _new_token()
    UserRepository(db).set_password(
        user_id, hash_password(password), session, must_change=False
    )
    db.commit()
    return _signed_in(session)


# ── Account ───────────────────────────────────────────────────────────────────

_ACCOUNT_SAVED = {"email": "Email saved."}


def _account_page(request: Request, user, status_code: int = 200, **ctx):
    return templates.TemplateResponse(
        request,
        "account.html",
        {"user": user, "email": user["email"] or "", **ctx},
        status_code=status_code,
    )


@router.get("/account", response_class=HTMLResponse)
def account_page(request: Request, user: User, saved: str = ""):
    if not user["has_password"]:
        return RedirectResponse("/auth/set-password", status_code=302)
    return _account_page(request, user, saved=_ACCOUNT_SAVED.get(saved))


@router.post("/account/email")
def set_account_email(
    request: Request,
    db: DB,
    user: User,
    current: str = Form(...),
    email: str = Form(""),
):
    """Add, change or clear your email. The current password is asked for
    because whoever controls the email can reset the password."""
    if not user["has_password"]:
        return RedirectResponse("/auth/set-password", status_code=302)
    user_repo = UserRepository(db)
    clean, error = clean_email(email)
    row = user_repo.get_login(user["username"] or "")
    if not error and not verify_password(
        row["password_hash"] if row else None, current
    ):
        error = "Your current password is wrong."
    if not error and clean and user_repo.email_taken(clean, user["id"]):
        error = "Another account has that email."
    if error:
        return _account_page(request, user, 400, email=email, email_error=error)

    try:
        user_repo.set_email(user["id"], clean)
        badges.award(db, user["id"])  # Email on File
        db.commit()
    except psycopg.errors.UniqueViolation:
        db.rollback()
        return _account_page(
            request,
            user,
            400,
            email=email,
            email_error="Another account has that email.",
        )
    return RedirectResponse("/account?saved=email", status_code=303)
