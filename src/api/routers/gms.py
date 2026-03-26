# src/api/routers/gms.py

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from src.api.database import get_db
from src.api.schemas import (
    GMAwayUpdate,
    GMEvaluationResponse,
    GMProfileResponse,
    GMProfileUpdate,
    GMResponse,
    PlayerGrades,
    player_row_to_grades,
)

router = APIRouter(prefix="/gms", tags=["gms"])

DB = Annotated[sqlite3.Connection, Depends(get_db)]


# ── Auth helper ───────────────────────────────────────────────────────────────


def _require_gm(
    gm_id: str,
    db: sqlite3.Connection,
    x_gm_session: str | None,
) -> sqlite3.Row:
    """
    Fetch a GM row and verify the session token.
    v1 auth: token is passed in X-GM-Session header.
    """
    gm = db.execute("SELECT * FROM gms WHERE id = ?", (gm_id,)).fetchone()
    if not gm:
        raise HTTPException(status_code=404, detail="GM not found.")
    if gm["user_session"] != x_gm_session:
        raise HTTPException(status_code=403, detail="Invalid session token.")
    return gm


# ── GET /gms/{gm_id} ─────────────────────────────────────────────────────────


@router.get("/{gm_id}")
def get_gm(gm_id: str, db: DB) -> GMResponse:
    row = db.execute("SELECT * FROM gms WHERE id = ?", (gm_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="GM not found.")
    return GMResponse(**_gm_dict(row))


# ── GET /gms/{gm_id}/profile ──────────────────────────────────────────────────


@router.get("/{gm_id}/profile")
def get_profile(gm_id: str, db: DB) -> GMProfileResponse:
    row = db.execute("SELECT * FROM gm_profiles WHERE gm_id = ?", (gm_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Profile not found.")
    return GMProfileResponse(**dict(row))


# ── PATCH /gms/{gm_id}/profile ───────────────────────────────────────────────


@router.patch("/{gm_id}/profile")
def update_profile(
    gm_id: str,
    body: GMProfileUpdate,
    db: DB,
    x_gm_session: str | None = Header(default=None),
) -> GMProfileResponse:
    """
    Update one or more strategic profile fields. All fields are optional.
    Only the owning GM (verified via X-GM-Session) may update their profile.
    """
    _require_gm(gm_id, db, x_gm_session)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=422, detail="No fields to update.")

    # Coerce bool → int for dh_enabled
    if "dh_enabled" in updates:
        updates["dh_enabled"] = int(updates["dh_enabled"])

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values()) + ["datetime('now')", gm_id]

    db.execute(
        f"UPDATE gm_profiles SET {set_clause}, updated_at = ? WHERE gm_id = ?",
        values,
    )

    row = db.execute("SELECT * FROM gm_profiles WHERE gm_id = ?", (gm_id,)).fetchone()
    return GMProfileResponse(**dict(row))


# ── PATCH /gms/{gm_id}/away ───────────────────────────────────────────────────


@router.patch("/{gm_id}/away")
def set_away(
    gm_id: str,
    body: GMAwayUpdate,
    db: DB,
    x_gm_session: str | None = Header(default=None),
) -> GMResponse:
    """Toggle the GM's away status. Away GMs hand off to AI without penalty."""
    _require_gm(gm_id, db, x_gm_session)

    db.execute(
        "UPDATE gms SET is_away = ? WHERE id = ?",
        (int(body.is_away), gm_id),
    )
    row = db.execute("SELECT * FROM gms WHERE id = ?", (gm_id,)).fetchone()
    return GMResponse(**_gm_dict(row))


# ── GET /gms/{gm_id}/roster ───────────────────────────────────────────────────


@router.get("/{gm_id}/roster")
def get_roster(gm_id: str, db: DB) -> list[PlayerGrades]:
    """
    Returns the GM's team roster with scouting grades.
    Active (26-man) players are listed first, then 40-man, then minors.
    """
    gm = db.execute("SELECT team_id FROM gms WHERE id = ?", (gm_id,)).fetchone()
    if not gm:
        raise HTTPException(status_code=404, detail="GM not found.")
    if not gm["team_id"]:
        return []

    team_id = gm["team_id"]

    rows = db.execute(
        """
        SELECT
            p.id, p.first_name, p.last_name, p.bats, p.throws, p.position,
            ps_status.status
        FROM team_players tp
        JOIN players p ON p.id = tp.player_id
        LEFT JOIN player_status ps_status ON ps_status.player_id = p.id
        WHERE tp.team_id = ?
        ORDER BY
            CASE ps_status.status
                WHEN '26man' THEN 1
                WHEN '40man' THEN 2
                WHEN 'minors' THEN 3
                ELSE 4
            END,
            p.last_name, p.first_name
        """,
        (team_id,),
    ).fetchall()

    result = []
    for row in rows:
        skills_row = db.execute(
            "SELECT * FROM player_skills WHERE player_id = ?", (row["id"],)
        ).fetchone()
        skills = dict(skills_row) if skills_row else {}
        result.append(
            player_row_to_grades(
                player=dict(row),
                skills=skills,
                status=row["status"] or "unassigned",
            )
        )

    return result


# ── GET /gms/{gm_id}/evaluations ─────────────────────────────────────────────


@router.get("/{gm_id}/evaluations")
def get_evaluations(gm_id: str, db: DB) -> list[GMEvaluationResponse]:
    """Return all season-end evaluations for this GM, most recent first."""
    rows = db.execute(
        """
        SELECT * FROM gm_season_evaluations
        WHERE gm_id = ?
        ORDER BY evaluated_at DESC
        """,
        (gm_id,),
    ).fetchall()

    return [
        GMEvaluationResponse(
            **{
                **dict(r),
                "made_playoffs": bool(r["made_playoffs"]),
                "won_championship": bool(r["won_championship"]),
            }
        )
        for r in rows
    ]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _gm_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["is_ai"] = bool(d["is_ai"])
    d["is_away"] = bool(d["is_away"])
    d.pop("user_session", None)  # never leak session in GET responses
    return d
