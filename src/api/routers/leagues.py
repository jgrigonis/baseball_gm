# src/api/routers/leagues.py

from __future__ import annotations

import random
import sqlite3
import string
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header, status

from src.api.auth import resolve_commissioner
from src.api.database import get_db
from src.api.schemas import (
    GMResponse,
    LeagueCreate,
    LeagueJoin,
    LeagueResponse,
)
from src.api.services.league_start import start_league as _start

router = APIRouter(prefix="/leagues", tags=["leagues"])

DB = Annotated[sqlite3.Connection, Depends(get_db)]

_JOIN_CODE_CHARS = string.ascii_uppercase + string.digits
_JOIN_CODE_LEN = 6


def _make_join_code(db: sqlite3.Connection) -> str:
    """Generate a unique 6-character alphanumeric join code."""
    for _ in range(20):  # give up after 20 collisions (astronomically unlikely)
        code = "".join(random.choices(_JOIN_CODE_CHARS, k=_JOIN_CODE_LEN))
        exists = db.execute(
            "SELECT 1 FROM leagues WHERE join_code = %s", (code,)
        ).fetchone()
        if not exists:
            return code
    raise RuntimeError("Could not generate a unique join code.")


def _make_session_token() -> str:
    return uuid.uuid4().hex + uuid.uuid4().hex  # 64 hex chars


# ── POST /leagues ─────────────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_201_CREATED)
def create_league(body: LeagueCreate, db: DB) -> dict:
    """
    Create a new league. The caller becomes the commissioner.
    Returns the league + the commissioner GM (including their session token).
    """
    league_id = str(uuid.uuid4())
    gm_id = str(uuid.uuid4())
    join_code = _make_join_code(db)
    session_token = _make_session_token()

    db.execute(
        """
        INSERT INTO leagues (
            id, name, join_code, mode, num_teams, decision_window_sec,
            reentry_enabled, pace_control, state
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'lobby')
        """,
        (
            league_id,
            body.name,
            join_code,
            body.mode,
            body.num_teams,
            body.decision_window_sec,
            int(body.reentry_enabled),
            body.pace_control,
        ),
    )

    # Upsert user row for this session token
    db.execute(
        """INSERT INTO users (id, session_token, display_name)
           VALUES (%s, %s, %s)
           ON CONFLICT (session_token) DO UPDATE SET display_name = excluded.display_name""",
        (
            str(__import__("uuid").uuid4()),
            session_token,
            body.commissioner_display_name,
        ),
    )
    user = db.execute(
        "SELECT id FROM users WHERE session_token = %s", (session_token,)
    ).fetchone()
    db.execute(
        "INSERT INTO gms (id, league_id, user_id, display_name, is_ai) VALUES (%s, %s, %s, %s, 0)",
        (gm_id, league_id, user["id"], body.commissioner_display_name),
    )

    # Create default strategic profile for commissioner
    db.execute("INSERT INTO gm_profiles (gm_id) VALUES (%s)", (gm_id,))

    db.execute(
        "UPDATE leagues SET commissioner_gm_id = %s WHERE id = %s", (gm_id, league_id)
    )

    league = db.execute("SELECT * FROM leagues WHERE id = %s", (league_id,)).fetchone()
    gm = db.execute("SELECT * FROM gms WHERE id = %s", (gm_id,)).fetchone()

    return {
        "league": _league_row(league),
        "gm": {**_gm_row(gm), "user_session": session_token},
    }


# ── GET /leagues/{join_code} ──────────────────────────────────────────────────


@router.get("/{join_code}")
def get_league(join_code: str, db: DB) -> LeagueResponse:
    """Look up a league by its join code."""
    row = db.execute(
        "SELECT * FROM leagues WHERE join_code = %s", (join_code.upper(),)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="League not found.")
    return LeagueResponse(**_league_row(row))


# ── GET /leagues/{join_code}/gms ──────────────────────────────────────────────


@router.get("/{join_code}/gms")
def list_gms(join_code: str, db: DB) -> list[dict]:
    """List all GMs in a league (human and AI), without session tokens."""
    league = db.execute(
        "SELECT id FROM leagues WHERE join_code = %s", (join_code.upper(),)
    ).fetchone()
    if not league:
        raise HTTPException(status_code=404, detail="League not found.")

    rows = db.execute(
        "SELECT * FROM gms WHERE league_id = %s ORDER BY created_at",
        (league["id"],),
    ).fetchall()

    return [_gm_row(r) for r in rows]


# ── POST /leagues/{join_code}/join ────────────────────────────────────────────


@router.post("/{join_code}/join", status_code=status.HTTP_201_CREATED)
def join_league(join_code: str, body: LeagueJoin, db: DB) -> GMResponse:
    """
    Join an existing league as a human GM. Returns the new GM including
    their session token — store it, it won't be shown again.
    """
    league = db.execute(
        "SELECT * FROM leagues WHERE join_code = %s", (join_code.upper(),)
    ).fetchone()
    if not league:
        raise HTTPException(status_code=404, detail="League not found.")

    if league["state"] != "lobby":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"League has already started (state: {league['state']}).",
        )

    # Count current human GMs — cap at num_teams
    human_count = db.execute(
        "SELECT COUNT(*) FROM gms WHERE league_id = %s AND is_ai = 0",
        (league["id"],),
    ).fetchone()["count"]

    if human_count >= league["num_teams"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="League is full.",
        )

    gm_id = str(uuid.uuid4())
    session_token = _make_session_token()

    # Upsert user row for this session token
    db.execute(
        """INSERT INTO users (id, session_token, display_name)
           VALUES (%s, %s, %s)
           ON CONFLICT (session_token) DO UPDATE SET display_name = excluded.display_name""",
        (str(__import__("uuid").uuid4()), session_token, body.display_name),
    )
    user = db.execute(
        "SELECT id FROM users WHERE session_token = %s", (session_token,)
    ).fetchone()
    db.execute(
        "INSERT INTO gms (id, league_id, user_id, display_name, is_ai) VALUES (%s, %s, %s, %s, 0)",
        (gm_id, league["id"], user["id"], body.display_name),
    )

    db.execute("INSERT INTO gm_profiles (gm_id) VALUES (%s)", (gm_id,))

    gm = db.execute("SELECT * FROM gms WHERE id = %s", (gm_id,)).fetchone()
    return GMResponse(**{**_gm_row(gm), "user_session": session_token})


# ── POST /leagues/{league_id}/start ──────────────────────────────────────────


@router.post("/{league_id}/start", status_code=status.HTTP_200_OK)
def start_league(
    league_id: str,
    db: DB,
    x_gm_session: str | None = Header(default=None),
) -> dict:
    """
    Commissioner-only. Locks the lobby, generates teams, builds the schedule,
    fills AI GM slots, and opens the draft. League state advances to 'draft'.
    """
    # Verify caller is the commissioner
    league = db.execute("SELECT * FROM leagues WHERE id = %s", (league_id,)).fetchone()
    if not league:
        raise HTTPException(status_code=404, detail="League not found.")

    resolve_commissioner(db, x_gm_session, league_id)

    try:
        result = _start(league_id, db)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────


def _league_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["reentry_enabled"] = bool(d.get("reentry_enabled", 1))
    return d


def _gm_row(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["is_ai"] = bool(d["is_ai"])
    d["is_away"] = bool(d["is_away"])
    return d
