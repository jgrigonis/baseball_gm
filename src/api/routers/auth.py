# src/api/routers/auth.py
#
# Landing page and guest identity.
#
# Identity model (matches schema.py):
#   users.session_token  ← stored in "gm_session" browser cookie
#   users → gms          via gms.user_id (one gm row per league)
#
# So the resolution chain is:
#   cookie → users row → gms row WHERE league_id = ?
#
# Guest creation only makes a users row. The gms row is created when the
# user creates or joins a league (see leagues.py).

from __future__ import annotations

import uuid

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.api.dependencies import DB, OptionalUser
from src.db.repositories.user_repo import UserRepository
from src.web.utils import templates

router = APIRouter(tags=["web"])


@router.get("/", response_class=HTMLResponse)
def landing(request: Request, user: OptionalUser):
    if user:
        return RedirectResponse("/leagues/")
    return templates.TemplateResponse(request, "landing.html", {})


@router.post("/auth/guest")
def create_guest(
    db: DB,
    user: OptionalUser,
    display_name: str = Form(default="Guest"),
):
    """
    Create a guest identity (users row only).
    If a valid session cookie already exists, reuse that user rather than
    creating a new one — prevents identity fragmentation on repeat visits.
    """
    if user:
        return RedirectResponse("/leagues/", status_code=302)

    token = uuid.uuid4().hex + uuid.uuid4().hex
    user_id = str(uuid.uuid4())
    user_repo = UserRepository(db)
    user_repo.insert_user(user_id, token, display_name or "Guest")
    db.commit()
    resp = RedirectResponse("/leagues/", status_code=302)
    resp.set_cookie(
        "gm_session",
        token,
        max_age=60 * 60 * 24 * 365 * 5,
        httponly=True,
        samesite="lax",
    )
    return resp


@router.post("/auth/logout")
def logout(db: DB, user: OptionalUser):
    resp = RedirectResponse("/", status_code=302)
    resp.delete_cookie("gm_session", httponly=True, samesite="lax")

    if user:
        UserRepository(db).invalidate_session(user["id"])
        db.commit()
    return resp
