# src/api/dependencies.py
from typing import Annotated, Any
from fastapi import Request, Depends, Cookie, HTTPException

import psycopg

from src.api.database import get_db
from src.api.services.ready_check import is_multiplayer
from src.db.repositories.user_repo import UserRepository

# ── TYPE ALIAS (For clean route signatures) ────────────────────────────────
DB = Annotated[psycopg.Connection, Depends(get_db)]


# Your reusable dependency function
def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


class PasswordChangeRequired(HTTPException):
    """The user has to choose a new password before going on: the default
    admin, or someone whose password an admin set. Page loads are sent to the
    change-password page (see main.py)."""

    def __init__(self):
        super().__init__(status_code=403, detail="Choose a new password first.")


# Open to a user who still has to change their password.
_PASSWORD_CHANGE_PATHS = ("/auth/change-password", "/auth/logout")


def get_current_user(request: Request, db: DB, gm_session: str = Cookie(None)):
    user = UserRepository(db).get_by_token(gm_session)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in")
    if user["must_change_password"] and request.url.path not in _PASSWORD_CHANGE_PATHS:
        raise PasswordChangeRequired()
    # base.html reads this so every page's top bar knows who is signed in.
    request.state.user = user
    return user


def get_admin(user: Any = Depends(get_current_user)):
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Admins only")
    return user


def get_optional_user(request: Request, db: DB, gm_session: str = Cookie(None)):
    """Use this for public pages that change if you are logged in."""
    user = UserRepository(db).get_by_token(gm_session)
    request.state.user = user
    return user


class NotLeagueGM(HTTPException):
    """The user has no GM in this league, or the league no longer exists.
    Page loads are sent back to the league list (see main.py); API and fetch
    callers get the 403."""

    def __init__(self):
        super().__init__(status_code=403, detail="Not a GM in this league")


def get_current_gm(league_id: str, db: DB, user: Any = Depends(get_current_user)):
    # This automatically uses the 'user' we already resolved!
    gm = db.execute(
        "SELECT * FROM gms WHERE user_id = %s AND league_id = %s",
        (user["id"], league_id),
    ).fetchone()
    if not gm:
        raise NotLeagueGM()
    return gm


def get_gm_or_viewer(league_id: str, db: DB, user: Any = Depends(get_current_user)):
    """For read-only league pages. A GM gets their own row. Anyone else signed
    in can view a public league once it has started, and an admin any league
    that has started, as a viewer: a stand-in GM with no id and no team, so
    "your team" highlights and actions drop out."""
    gm = db.execute(
        "SELECT * FROM gms WHERE user_id = %s AND league_id = %s",
        (user["id"], league_id),
    ).fetchone()
    if gm:
        return gm
    league = db.execute(
        "SELECT is_public, state FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    can_view = league and (league["is_public"] or user.get("is_admin"))
    if not can_view or league["state"] == "lobby":
        raise NotLeagueGM()
    return {
        "id": None,
        "team_id": None,
        "display_name": user["display_name"],
        "is_viewer": True,
    }


def get_commissioner(league_id: str, db: DB, gm: Any = Depends(get_current_gm)):
    league = db.execute(
        "SELECT commissioner_gm_id FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if not league or league["commissioner_gm_id"] != gm["id"]:
        raise HTTPException(status_code=403, detail="Commissioner only")
    return gm


def require_single_player(league_id: str, db: DB):
    """For routes that advance the league on one GM's say. With several human
    GMs the league advances by ready-check instead."""
    if is_multiplayer(db, league_id):
        raise HTTPException(
            status_code=403, detail="This league advances when every GM is ready."
        )


def require_active_league(league_id: str, db: DB):
    """For routes that change a league. A complete league is read-only: its
    history and records stay viewable, but nothing in it changes."""
    league = db.execute(
        "SELECT state FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if league and league["state"] == "complete":
        raise HTTPException(status_code=409, detail="This league is complete.")


def require_unpaused(league_id: str, db: DB):
    """For routes that move a league on. An admin can pause a league, which
    holds it where it is until they resume it."""
    league = db.execute(
        "SELECT is_paused FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if league and league["is_paused"]:
        raise HTTPException(status_code=409, detail="An admin has paused this league.")


# ── TYPE ALIASES (For clean route signatures) ────────────────────────────────
IsHTMX = Annotated[bool, Depends(is_htmx)]

User = Annotated[Any, Depends(get_current_user)]
OptionalUser = Annotated[Any, Depends(get_optional_user)]
Admin = Annotated[Any, Depends(get_admin)]
GM = Annotated[Any, Depends(get_current_gm)]
GMOrViewer = Annotated[Any, Depends(get_gm_or_viewer)]
Commissioner = Annotated[Any, Depends(get_commissioner)]
SinglePlayer = Annotated[None, Depends(require_single_player)]
ActiveLeague = Annotated[None, Depends(require_active_league)]
Unpaused = Annotated[None, Depends(require_unpaused)]
