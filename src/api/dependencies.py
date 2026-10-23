# src/api/dependencies.py
from typing import Annotated, Any
from fastapi import Request, Depends, Cookie, HTTPException

import psycopg

from src.api.database import get_db
from src.db.repositories.user_repo import UserRepository

# ── TYPE ALIAS (For clean route signatures) ────────────────────────────────
DB = Annotated[psycopg.Connection, Depends(get_db)]

# Your reusable dependency function
def is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


async def get_current_user(db: DB, gm_session: str = Cookie(None)):
    user = UserRepository(db).get_by_token(gm_session)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in")
    return user


async def get_optional_user(db: DB, gm_session: str = Cookie(None)):
    """Use this for public pages that change if you are logged in."""
    return UserRepository(db).get_by_token(gm_session)


async def get_current_gm(league_id: str, db: DB, user: Any = Depends(get_current_user)):
    # This automatically uses the 'user' we already resolved!
    gm = db.execute(
        "SELECT * FROM gms WHERE user_id = %s AND league_id = %s",
        (user["id"], league_id),
    ).fetchone()
    if not gm:
        raise HTTPException(status_code=403, detail="Not a GM in this league")
    return gm


async def get_commissioner(league_id: str, db: DB, gm: Any = Depends(get_current_gm)):
    league = db.execute(
        "SELECT commissioner_gm_id FROM leagues WHERE id = %s", (league_id,)
    ).fetchone()
    if not league or league["commissioner_gm_id"] != gm["id"]:
        raise HTTPException(status_code=403, detail="Commissioner only")
    return gm


# ── TYPE ALIASES (For clean route signatures) ────────────────────────────────
IsHTMX = Annotated[bool, Depends(is_htmx)]

User = Annotated[Any, Depends(get_current_user)]
OptionalUser = Annotated[Any, Depends(get_optional_user)]
GM = Annotated[Any, Depends(get_current_gm)]
Commissioner = Annotated[Any, Depends(get_commissioner)]
