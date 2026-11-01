# src/api/routers/profiles.py
#
# GM profile pages (plans/gm-profile-page.md): one per person, at
# /gms/{username}, with their career across every league. Anyone signed in
# can see anyone's.

from __future__ import annotations

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.api.dependencies import DB, User
from src.api.view_models.profile import (
    BIO_MAX,
    favorite_team,
    find_user,
    profile_context,
    team_choices,
)
from src.db.repositories.user_repo import UserRepository
from src.web.utils import templates

router = APIRouter(tags=["web"])


@router.get("/gms/{username}", response_class=HTMLResponse)
def gm_profile(request: Request, username: str, db: DB, user: User):
    person = find_user(db, username)
    if not person:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "user": user,
                "status_code": 404,
                "message": "There's no GM by that name.",
            },
            status_code=404,
        )
    if person["username"] != username:
        # One address per person, as they spell it.
        return RedirectResponse(f"/gms/{person['username']}", status_code=301)
    ctx = profile_context(db, person, user)
    return templates.TemplateResponse(request, "profile.html", {"user": user, **ctx})


def _edit_page(request, user, bio: str, favorite: str, error=None, status_code=200):
    return templates.TemplateResponse(
        request,
        "profile_edit.html",
        {
            "user": user,
            "bio": bio,
            "favorite": favorite,
            "teams": team_choices(),
            "bio_max": BIO_MAX,
            "error": error,
        },
        status_code=status_code,
    )


@router.get("/profile/edit", response_class=HTMLResponse)
def edit_profile_page(request: Request, db: DB, user: User):
    """Your bio and favorite team. Only people with a username have a
    profile to edit."""
    if not user.get("username"):
        return RedirectResponse("/", status_code=302)
    person = find_user(db, user["username"])
    return _edit_page(request, user, person["bio"] or "", person["favorite_team"] or "")


@router.post("/profile/edit")
def edit_profile(
    request: Request,
    db: DB,
    user: User,
    bio: str = Form(""),
    favorite_team_city: str = Form(""),
):
    if not user.get("username"):
        return RedirectResponse("/", status_code=302)
    clean = " ".join(bio.split())  # one line
    if len(clean) > BIO_MAX:
        return _edit_page(
            request,
            user,
            clean,
            favorite_team_city,
            f"Keep the bio to {BIO_MAX} characters.",
            400,
        )
    if favorite_team_city and not favorite_team(favorite_team_city):
        return _edit_page(request, user, clean, "", "Pick a team from the list.", 400)
    UserRepository(db).set_profile(
        user["id"], clean or None, favorite_team_city or None
    )
    db.commit()
    return RedirectResponse(f"/gms/{user['username']}", status_code=303)
