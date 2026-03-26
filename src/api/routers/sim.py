# src/api/routers/sim.py

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status

from src.api.database import get_db

router = APIRouter(prefix="/leagues", tags=["sim"])

DB = Annotated[sqlite3.Connection, Depends(get_db)]


@router.post("/{league_id}/sim/next", status_code=status.HTTP_200_OK)
def sim_next(
    league_id: str,
    db: DB,
    x_gm_session: str | None = Header(default=None),
) -> dict:
    """
    Play the next unplayed day of games for this league.
    Any GM in the league can trigger this (not commissioner-only)
    so the sim can advance even if the commissioner is away.
    """
    # Verify caller is a GM in this league
    if x_gm_session:
        gm = db.execute(
            "SELECT * FROM gms WHERE user_session = ? AND league_id = ?",
            (x_gm_session, league_id),
        ).fetchone()
        if not gm:
            raise HTTPException(status_code=403, detail="Not a member of this league.")

    try:
        from src.api.services.sim_next import sim_next_day

        return sim_next_day(league_id, db)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
