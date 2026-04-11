# src/api/routers/draft.py
#
# Handles both draft formats:
#   preference  — blitz: GMs submit ranked lists, draft runs automatically
#   interactive — longform: live snake draft with per-pick timer

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

from src.api.database import get_db
from src.api.schemas import (
    DraftPickResponse,
    DraftResponse,
    PlayerGrades,
    PreferenceListResponse,
    PreferenceListSubmit,
    player_row_to_grades,
)

router = APIRouter(prefix="/drafts", tags=["draft"])

DB = Annotated[Any, Depends(get_db)]


# ── Auth helper (shared with gms router) ─────────────────────────────────────


def _resolve_gm(db, x_gm_session: str | None):
    if not x_gm_session:
        raise HTTPException(status_code=401, detail="X-GM-Session header required.")
    gm = db.execute(
        "SELECT * FROM gms WHERE user_session = %s", (x_gm_session,)
    ).fetchone()
    if not gm:
        raise HTTPException(status_code=403, detail="Invalid session token.")
    return gm


# ── GET /drafts/{draft_id} ────────────────────────────────────────────────────


@router.get("/{draft_id}")
def get_draft(draft_id: str, db: DB) -> DraftResponse:
    row = db.execute("SELECT * FROM drafts WHERE id = %s", (draft_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return DraftResponse(**dict(row))


# ── GET /drafts/{draft_id}/picks ──────────────────────────────────────────────


@router.get("/{draft_id}/picks")
def get_picks(draft_id: str, db: DB) -> list[DraftPickResponse]:
    """All picks made so far, in pick order."""
    _require_draft(draft_id, db)
    rows = db.execute(
        "SELECT * FROM draft_picks WHERE draft_id = %s ORDER BY pick_number",
        (draft_id,),
    ).fetchall()
    return [
        DraftPickResponse(**{**dict(r), "auto_picked": bool(r["auto_picked"])})
        for r in rows
    ]


# ── GET /drafts/{draft_id}/board ──────────────────────────────────────────────


@router.get("/{draft_id}/board")
def get_board(draft_id: str, db: DB) -> list[PlayerGrades]:
    """
    All available (undrafted) players for this draft, with scouting grades.
    Useful for building preference lists and for the interactive draft room.
    """
    # draft = _require_draft(draft_id, db)

    # Players already picked in this draft
    picked_ids = {
        r["player_id"]
        for r in db.execute(
            "SELECT player_id FROM draft_picks WHERE draft_id = %s", (draft_id,)
        ).fetchall()
    }

    _ = _require_draft(draft_id, db)

    all_players = db.execute(
        """
        SELECT p.*, ps.status
        FROM players p
        JOIN player_status ps ON ps.player_id = p.id
        WHERE ps.status IN ('free_agent', 'unassigned', 'prospect')
        AND p.league_id = (SELECT league_id FROM drafts WHERE id = %s)
        ORDER BY p.last_name, p.first_name
        """,
        (draft_id,),
    ).fetchall()

    board = []
    for row in all_players:
        if row["id"] in picked_ids:
            continue
        skills_row = db.execute(
            "SELECT * FROM player_skills WHERE player_id = %s", (row["id"],)
        ).fetchone()
        skills = dict(skills_row) if skills_row else {}
        board.append(
            player_row_to_grades(
                player=dict(row),
                skills=skills,
                status=row["status"] or "unassigned",
            )
        )

    return board


# ── PUT /drafts/{draft_id}/preferences ────────────────────────────────────────


@router.put("/{draft_id}/preferences", status_code=status.HTTP_200_OK)
def submit_preferences(
    draft_id: str,
    body: PreferenceListSubmit,
    db: DB,
    x_gm_session: str | None = Header(default=None),
) -> PreferenceListResponse:
    """
    Submit (or replace) a ranked preference list for the blitz draft.
    Can also be called in interactive drafts to set the auto-pick fallback.
    The list may be updated any time before the draft completes.
    """
    draft = _require_draft(draft_id, db)
    if draft["state"] == "complete":
        raise HTTPException(status_code=409, detail="Draft is already complete.")

    gm = _resolve_gm(db, x_gm_session)

    # Validate all player IDs exist
    for pid in body.player_ids:
        exists = db.execute("SELECT 1 FROM players WHERE id = %s", (pid,)).fetchone()
        if not exists:
            raise HTTPException(status_code=422, detail=f"Unknown player id: {pid}")

    # Replace existing preferences atomically
    db.execute(
        "DELETE FROM draft_preferences WHERE gm_id = %s AND draft_id = %s",
        (gm["id"], draft_id),
    )
    db.cursor().executemany(
        "INSERT INTO draft_preferences (gm_id, draft_id, player_id, rank) VALUES (%s, %s, %s, %s)",
        [
            (gm["id"], draft_id, pid, rank + 1)
            for rank, pid in enumerate(body.player_ids)
        ],
    )

    return PreferenceListResponse(
        gm_id=gm["id"],
        draft_id=draft_id,
        preferences=body.player_ids,
    )


# ── GET /drafts/{draft_id}/preferences ────────────────────────────────────────


@router.get("/{draft_id}/preferences")
def get_preferences(
    draft_id: str,
    db: DB,
    x_gm_session: str | None = Header(default=None),
) -> PreferenceListResponse:
    """Return the calling GM's current preference list for this draft."""
    _require_draft(draft_id, db)
    gm = _resolve_gm(db, x_gm_session)

    rows = db.execute(
        """
        SELECT player_id FROM draft_preferences
        WHERE gm_id = %s AND draft_id = %s
        ORDER BY rank
        """,
        (gm["id"], draft_id),
    ).fetchall()

    return PreferenceListResponse(
        gm_id=gm["id"],
        draft_id=draft_id,
        preferences=[r["player_id"] for r in rows],
    )


# ── POST /drafts/{draft_id}/pick ──────────────────────────────────────────────


@router.post("/{draft_id}/pick", status_code=status.HTTP_201_CREATED)
def make_pick(
    draft_id: str,
    player_id: str,
    db: DB,
    x_gm_session: str | None = Header(default=None),
) -> DraftPickResponse:
    """
    Make a pick in an interactive draft. Only valid when it's the calling GM's
    turn. Blitz drafts use the preference-list auto-draft instead.
    """
    draft = _require_draft(draft_id, db)

    if draft["format"] != "interactive":
        raise HTTPException(
            status_code=409,
            detail="This is a preference-list draft — picks are made automatically.",
        )
    if draft["state"] != "open":
        raise HTTPException(
            status_code=409, detail=f"Draft state is '{draft['state']}'."
        )

    gm = _resolve_gm(db, x_gm_session)

    # Verify it's this GM's turn
    expected_gm_id = _gm_on_the_clock(draft, db)
    if gm["id"] != expected_gm_id:
        raise HTTPException(status_code=409, detail="It's not your pick.")

    # Verify player is available
    already_picked = db.execute(
        "SELECT 1 FROM draft_picks WHERE draft_id = %s AND player_id = %s",
        (draft_id, player_id),
    ).fetchone()
    if already_picked:
        raise HTTPException(status_code=409, detail="Player already picked.")

    pick_number = draft["current_pick"]
    num_teams = db.execute(
        "SELECT num_teams FROM leagues WHERE id = %s", (draft["league_id"],)
    ).fetchone()["num_teams"]
    round_number = ((pick_number - 1) // num_teams) + 1

    db.execute(
        """
        INSERT INTO draft_picks
            (draft_id, pick_number, round, gm_id, team_id, player_id, auto_picked)
        VALUES (%s, %s, %s, %s, %s, %s, 0)
        """,
        (draft_id, pick_number, round_number, gm["id"], gm["team_id"], player_id),
    )
    db.execute(
        "UPDATE drafts SET current_pick = current_pick + 1 WHERE id = %s",
        (draft_id,),
    )

    row = db.execute(
        "SELECT * FROM draft_picks WHERE draft_id = %s AND pick_number = %s",
        (draft_id, pick_number),
    ).fetchone()
    return DraftPickResponse(**{**dict(row), "auto_picked": False})


# ── POST /drafts/{draft_id}/execute ──────────────────────────────────────────────


@router.post("/{draft_id}/execute", status_code=status.HTTP_200_OK)
def execute_draft(
    draft_id: str,
    db: DB,
    x_gm_session: str | None = Header(default=None),
) -> dict:
    """
    Commissioner-only. Runs the full blitz preference-list auto-draft in one
    shot. League state advances to 'preseason' on completion.
    """
    draft = _require_draft(draft_id, db)

    league = db.execute(
        "SELECT * FROM leagues WHERE id = %s", (draft["league_id"],)
    ).fetchone()
    commissioner = db.execute(
        "SELECT * FROM gms WHERE id = %s", (league["commissioner_gm_id"],)
    ).fetchone()
    if not commissioner or commissioner["user_session"] != x_gm_session:
        raise HTTPException(
            status_code=403, detail="Only the commissioner can execute the draft."
        )

    try:
        from src.api.services.draft_execute import execute_blitz_draft

        return execute_blitz_draft(draft_id, db)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _require_draft(draft_id: str, db):
    row = db.execute("SELECT * FROM drafts WHERE id = %s", (draft_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Draft not found.")
    return row


def _gm_on_the_clock(draft, db) -> str | None:
    """
    Determine which GM should pick next in snake order.
    Returns the GM id, or None if the draft is over.
    """
    pick_number = draft["current_pick"]
    league_id = draft["league_id"]

    # Ordered list of GMs (human + AI, in join order)
    gms = db.execute(
        "SELECT id FROM gms WHERE league_id = %s ORDER BY created_at",
        (league_id,),
    ).fetchall()

    if not gms:
        return None

    n = len(gms)
    zero_idx = pick_number - 1
    round_num = zero_idx // n  # 0-based round

    if round_num % 2 == 0:
        # Forward round
        pos = zero_idx % n
    else:
        # Reverse (snake) round
        pos = n - 1 - (zero_idx % n)

    return gms[pos]["id"]
