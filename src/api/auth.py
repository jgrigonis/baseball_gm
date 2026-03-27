# src/api/auth.py
#
# Shared authentication helpers for all API routers.
#
# Identity chain:
#   X-GM-Session header → users.session_token → users.id
#                       → gms WHERE user_id = ? AND league_id = ?
#
# Two entry points:
#   resolve_gm_for_league  — used when you have a league_id in scope
#   require_gm_by_id       — used on /gms/{gm_id} routes where the
#                            caller proves ownership of a specific GM row

from __future__ import annotations

import sqlite3

from fastapi import HTTPException, status


def _resolve_user(db: sqlite3.Connection, session_token: str | None) -> sqlite3.Row:
    """
    session_token → users row.
    Raises 401 if missing, 403 if not found.
    """
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="X-GM-Session header required.",
        )
    user = db.execute(
        "SELECT * FROM users WHERE session_token = ?", (session_token,)
    ).fetchone()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid session token.",
        )
    return user


def resolve_gm_for_league(
    db: sqlite3.Connection,
    session_token: str | None,
    league_id: str,
) -> sqlite3.Row:
    """
    Resolve the GM row for this session in a specific league.
    Used by draft routes and any route scoped to a league_id.

    Raises 401 if no session, 403 if session invalid or not a GM in this league.
    """
    user = _resolve_user(db, session_token)
    gm = db.execute(
        "SELECT * FROM gms WHERE user_id = ? AND league_id = ?",
        (user["id"], league_id),
    ).fetchone()
    if not gm:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a GM in this league.",
        )
    return gm


def require_gm_by_id(
    db: sqlite3.Connection,
    gm_id: str,
    session_token: str | None,
) -> sqlite3.Row:
    """
    Fetch a GM row by id and verify the session owns it.
    Used by /gms/{gm_id}/... routes where the GM id is explicit in the URL.

    Raises 404 if GM not found, 403 if session doesn't match.
    """
    gm = db.execute("SELECT * FROM gms WHERE id = ?", (gm_id,)).fetchone()
    if not gm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="GM not found."
        )

    # AI GMs have no user_id — can never be claimed via session
    if not gm["user_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid session token."
        )

    user = _resolve_user(db, session_token)
    if gm["user_id"] != user["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid session token."
        )

    return gm


def resolve_commissioner(
    db: sqlite3.Connection,
    session_token: str | None,
    league_id: str,
) -> sqlite3.Row:
    """
    Like resolve_gm_for_league but also asserts the GM is the commissioner.
    Used by league start, draft execute, and other commissioner-only actions.
    """
    gm = resolve_gm_for_league(db, session_token, league_id)
    league = db.execute(
        "SELECT commissioner_gm_id FROM leagues WHERE id = ?", (league_id,)
    ).fetchone()
    if not league or league["commissioner_gm_id"] != gm["id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the commissioner can perform this action.",
        )
    return gm
