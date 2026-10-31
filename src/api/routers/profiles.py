# src/api/routers/profiles.py
#
# GM profile pages (plans/gm-profile-page.md): one per person, at
# /gms/{username}, with their career across every league. Anyone signed in
# can see anyone's.

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from src.api.dependencies import DB, User
from src.api.view_models.profile import find_user, profile_context
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
