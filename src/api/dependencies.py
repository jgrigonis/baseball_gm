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


def get_current_user(db: DB, gm_session: str = Cookie(None)):
    user = UserRepository(db).get_by_token(gm_session)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in")
    return user


def get_optional_user(db: DB, gm_session: str = Cookie(None)):
    """Use this for public pages that change if you are logged in."""
    return UserRepository(db).get_by_token(gm_session)


def get_current_gm(league_id: str, db: DB, user: Any = Depends(get_current_user)):
    # This automatically uses the 'user' we already resolved!
    gm = db.execute(
        "SELECT * FROM gms WHERE user_id = %s AND league_id = %s",
        (user["id"], league_id),
    ).fetchone()
    if not gm:
        raise HTTPException(status_code=403, detail="Not a GM in this league")
    return gm


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


# ── TYPE ALIASES (For clean route signatures) ────────────────────────────────
IsHTMX = Annotated[bool, Depends(is_htmx)]

User = Annotated[Any, Depends(get_current_user)]
OptionalUser = Annotated[Any, Depends(get_optional_user)]
GM = Annotated[Any, Depends(get_current_gm)]
Commissioner = Annotated[Any, Depends(get_commissioner)]
SinglePlayer = Annotated[None, Depends(require_single_player)]
ActiveLeague = Annotated[None, Depends(require_active_league)]
