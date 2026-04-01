# src/api/routers/gms.py

from __future__ import annotations

import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException

from src.api.auth import require_gm_by_id
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
    require_gm_by_id(db, gm_id, x_gm_session)

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
    require_gm_by_id(db, gm_id, x_gm_session)

    db.execute(
        "UPDATE gms SET is_away = ? WHERE id = ?",
        (int(body.is_away), gm_id),
    )
    row = db.execute("SELECT * FROM gms WHERE id = ?", (gm_id,)).fetchone()
    return GMResponse(**_gm_dict(row))


# ── GET /gms/{gm_id}/roster ───────────────────────────────────────────────────


@router.get("/{gm_id}/roster")
def get_roster(gm_id: str, db: DB) -> list[PlayerGrades]:
    gm = db.execute(
        "SELECT team_id, league_id FROM gms WHERE id = ?", (gm_id,)
    ).fetchone()
    if not gm:
        raise HTTPException(status_code=404, detail="GM not found.")
    if not gm["team_id"]:
        return []

    team_id = gm["team_id"]

    # Scope to the current season so players from previous leagues don't bleed in
    season_row = db.execute(
        """
        SELECT season_id FROM league_seasons
        WHERE league_id = ? ORDER BY rowid DESC LIMIT 1
        """,
        (gm["league_id"],),
    ).fetchone()
    if not season_row:
        return []
    season_id = season_row["season_id"]

    rows = db.execute(
        """
        SELECT
            p.id, p.first_name, p.last_name, p.bats, p.throws, p.position,
            ps_status.status
        FROM league_season_teams lst
        JOIN team_players tp ON tp.team_id = lst.team_id
        JOIN players p ON p.id = tp.player_id
        LEFT JOIN player_status ps_status ON ps_status.player_id = p.id
        WHERE lst.team_id = ? AND lst.season_id = ?
        ORDER BY
            CASE ps_status.status
                WHEN '26man' THEN 1
                WHEN '40man' THEN 2
                WHEN 'minors' THEN 3
                ELSE 4
            END,
            p.last_name, p.first_name
        """,
        (team_id, season_id),
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


# ── PATCH /gms/{gm_id}/roster ─────────────────────────────────────────────────


@router.patch("/{gm_id}/roster")
def set_roster(
    gm_id: str,
    body: dict,
    db: DB,
    x_gm_session: str | None = Header(default=None),
) -> dict:
    """
    Set 26-man active roster. Body: {"active": ["player_id", ...]}
    Players on the list get status '26man', others on the team drop to '40man'.
    Max 26 players in active list.
    """
    require_gm_by_id(db, gm_id, x_gm_session)

    active_ids = body.get("active", [])
    if len(active_ids) > 26:
        raise HTTPException(
            status_code=422, detail="Cannot have more than 26 active players."
        )

    gm = db.execute("SELECT team_id FROM gms WHERE id = ?", (gm_id,)).fetchone()
    if not gm or not gm["team_id"]:
        raise HTTPException(status_code=404, detail="GM has no team assigned.")

    team_id = gm["team_id"]
    active_set = set(active_ids)

    # Verify all players belong to this team
    team_players = {
        r["player_id"]
        for r in db.execute(
            """
            SELECT tp.player_id FROM league_season_teams lst
            JOIN team_players tp ON tp.team_id = lst.team_id
            WHERE lst.team_id = ? AND lst.season_id = (
                SELECT season_id FROM league_seasons
                WHERE league_id = (SELECT league_id FROM gms WHERE id = ?)
                ORDER BY rowid DESC LIMIT 1
            )
            """,
            (team_id, gm_id),
        ).fetchall()
    }

    invalid = active_set - team_players
    if invalid:
        raise HTTPException(
            status_code=422, detail=f"Players not on this team: {list(invalid)[:3]}"
        )

    now = db.execute("SELECT datetime('now')").fetchone()[0]

    for player_id in team_players:
        status = "26man" if player_id in active_set else "40man"
        db.execute(
            """
            INSERT INTO player_status (player_id, status, since)
            VALUES (?, ?, ?)
            ON CONFLICT (player_id) DO UPDATE SET status = ?, since = ?
            """,
            (player_id, status, now, status, now),
        )

    return {"active_count": len(active_set), "roster_size": len(team_players)}


# ── GET /gms/{gm_id}/lineup ───────────────────────────────────────────────────


@router.get("/{gm_id}/lineup")
def get_lineup(gm_id: str, db: DB) -> list[dict]:
    """Return the GM's stored lineup preferences."""
    rows = db.execute(
        """
        SELECT lp.player_id, lp.batting_order, lp.position, lp.is_starter,
               p.first_name, p.last_name
        FROM gm_lineup_preferences lp
        JOIN players p ON p.id = lp.player_id
        WHERE lp.gm_id = ?
        ORDER BY lp.batting_order ASC NULLS LAST, p.last_name
        """,
        (gm_id,),
    ).fetchall()

    return [dict(r) for r in rows]


# ── PATCH /gms/{gm_id}/lineup ─────────────────────────────────────────────────


@router.patch("/{gm_id}/lineup")
def set_lineup(
    gm_id: str,
    body: dict,
    db: DB,
    x_gm_session: str | None = Header(default=None),
) -> dict:
    """
    Store batting order + position assignments.
    Body: {"lineup": [{"player_id": "...", "batting_order": 1, "position": "cf", "is_starter": true}, ...]}
    Replaces the entire stored lineup.
    """
    require_gm_by_id(db, gm_id, x_gm_session)

    slots = body.get("lineup", [])

    # Validate batting orders 1-9, no duplicates
    orders = [s["batting_order"] for s in slots if s.get("batting_order")]
    if len(orders) != len(set(orders)):
        raise HTTPException(
            status_code=422, detail="Duplicate batting order positions."
        )
    if any(o < 1 or o > 9 for o in orders):
        raise HTTPException(status_code=422, detail="Batting order must be 1-9.")

    now = db.execute("SELECT datetime('now')").fetchone()[0]

    # Replace entire lineup
    db.execute("DELETE FROM gm_lineup_preferences WHERE gm_id = ?", (gm_id,))

    for slot in slots:
        db.execute(
            """
            INSERT INTO gm_lineup_preferences
                (gm_id, player_id, batting_order, position, is_starter, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                gm_id,
                slot["player_id"],
                slot.get("batting_order"),
                slot.get("position"),
                int(slot.get("is_starter", True)),
                now,
            ),
        )

    return {"slots_saved": len(slots)}


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


# GET /gms/{gm_id}/players/{player_id}


@router.get("/{gm_id}/players/{player_id}")
def get_player_detail(gm_id: str, player_id: str, db: DB) -> dict:
    """
    Full player detail: all skill grades, energy state, and current season stats.
    """
    gm = db.execute(
        "SELECT team_id, league_id FROM gms WHERE id = ?", (gm_id,)
    ).fetchone()
    if not gm:
        raise HTTPException(status_code=404, detail="GM not found.")

    player = db.execute("SELECT * FROM players WHERE id = ?", (player_id,)).fetchone()
    if not player:
        raise HTTPException(status_code=404, detail="Player not found.")

    skills_row = db.execute(
        "SELECT * FROM player_skills WHERE player_id = ?", (player_id,)
    ).fetchone()
    skills = dict(skills_row) if skills_row else {}

    status_row = db.execute(
        "SELECT status FROM player_status WHERE player_id = ?", (player_id,)
    ).fetchone()
    status = status_row["status"] if status_row else "unassigned"

    from src.api.schemas import player_row_to_grades, skill_to_grade

    grades = player_row_to_grades(dict(player), skills, status)

    # ── All individual skill grades ───────────────────────────────────────────
    all_grades = {}
    skill_labels = {
        # Hitting
        "contact": ("Contact", "hitting"),
        "power": ("Power", "hitting"),
        "eye": ("Eye", "hitting"),
        "speed": ("Speed", "hitting"),
        "base_running": ("Baserunning", "hitting"),
        "bunting": ("Bunting", "hitting"),
        "clutch": ("Clutch", "hitting"),
        # Defense
        "catching": ("Catching", "defense"),
        "infield": ("Infield", "defense"),
        "outfield": ("Outfield", "defense"),
        "arm": ("Arm", "defense"),
        # Pitching
        "strikes": ("Stuff", "pitching"),
        "accuracy": ("Control", "pitching"),
        "stamina": ("Stamina", "pitching"),
        "recovery": ("Recovery", "pitching"),
        "ground_balls": ("Ground Balls", "pitching"),
        # General
        "durability": ("Durability", "general"),
    }
    for key, (label, category) in skill_labels.items():
        val = skills.get(key)
        all_grades[key] = {
            "label": label,
            "category": category,
            "grade": skill_to_grade(val) if val is not None else "?",
            "raw": val,
        }

    # ── Energy ────────────────────────────────────────────────────────────────
    energy = None
    is_pitcher = grades.player_type == "pitcher"

    if is_pitcher:
        ps = db.execute(
            "SELECT * FROM pitcher_state WHERE player_id = ?", (player_id,)
        ).fetchone()
        if ps:
            energy = {
                "current": round(ps["current_energy"] * 100),
                "max": round(ps["max_energy"] * 100),
                "consecutive_days": ps["consecutive_days"],
                "last_game_date": ps["last_game_date"],
                "last_pitch_count": ps["last_pitch_count"],
            }
    else:
        pe = db.execute(
            "SELECT * FROM player_energy WHERE player_id = ?", (player_id,)
        ).fetchone()
        if pe:
            energy = {
                "current": round(pe["current_energy"] * 100),
                "max": round(pe["max_energy"] * 100),
                "consecutive_days": pe["consecutive_days"],
                "last_game_date": pe["last_game_date"],
                "season_games_played": pe["season_games_played"],
            }

    # ── Season stats ──────────────────────────────────────────────────────────
    season_row = db.execute(
        """
        SELECT season_id FROM league_seasons
        WHERE league_id = ? ORDER BY rowid DESC LIMIT 1
        """,
        (gm["league_id"],),
    ).fetchone()

    stats = None
    if season_row:
        season_id = season_row["season_id"]
        if is_pitcher:
            row = db.execute(
                """
                SELECT
                    COUNT(DISTINCT game_id) as G,
                    SUM(pitch_game_started) as GS,
                    SUM(pitch_win) as W, SUM(pitch_loss) as L,
                    SUM(pitch_save) as SV,
                    SUM(pitch_outs) as outs,
                    SUM(pitch_earned_runs) as ER,
                    SUM(pitch_hits) as H, SUM(pitch_walks) as BB,
                    SUM(pitch_strike_outs) as K
                FROM player_game_stats pgs
                JOIN games g ON g.id = pgs.game_id
                WHERE pgs.player_id = ? AND g.season_id = ?
                AND pgs.pitch_game_played = 1
                """,
                (player_id, season_id),
            ).fetchone()
            if row and row["G"]:
                ip = (row["outs"] or 0) / 3
                er = row["ER"] or 0
                bb = row["BB"] or 0
                k = row["K"] or 0
                h = row["H"] or 0
                era = round((er / ip) * 9, 2) if ip > 0 else None
                whip = round((bb + h) / ip, 3) if ip > 0 else None
                k9 = round((k / ip) * 9, 2) if ip > 0 else None
                bb9 = round((bb / ip) * 9, 2) if ip > 0 else None
                stats = {
                    "type": "pitching",
                    "G": row["G"],
                    "GS": row["GS"],
                    "W": row["W"],
                    "L": row["L"],
                    "SV": row["SV"],
                    "IP": round(ip, 1),
                    "ERA": era,
                    "WHIP": whip,
                    "K": k,
                    "BB": bb,
                    "K/9": k9,
                    "BB/9": bb9,
                }
        else:
            row = db.execute(
                """
                SELECT
                    COUNT(DISTINCT game_id) as G,
                    SUM(bat_ab) as AB, SUM(bat_hits) as H,
                    SUM(bat_doubles) as D2, SUM(bat_triples) as D3,
                    SUM(bat_home_runs) as HR, SUM(bat_rbi) as RBI,
                    SUM(bat_runs) as R, SUM(bat_walks) as BB,
                    SUM(bat_strike_outs) as K, SUM(bat_stolen_bases) as SB,
                    SUM(bat_hbp) as HBP, SUM(bat_sac_flys) as SF
                FROM player_game_stats pgs
                JOIN games g ON g.id = pgs.game_id
                WHERE pgs.player_id = ? AND g.season_id = ?
                AND pgs.bat_game_played = 1
                """,
                (player_id, season_id),
            ).fetchone()
            if row and row["G"]:
                ab = row["AB"] or 0
                h = row["H"] or 0
                bb = row["BB"] or 0
                hbp = row["HBP"] or 0
                sf = row["SF"] or 0
                tb = h + (row["D2"] or 0) + 2 * (row["D3"] or 0) + 3 * (row["HR"] or 0)
                avg = round(h / ab, 3) if ab > 0 else None
                obp = (
                    round((h + bb + hbp) / (ab + bb + hbp + sf), 3)
                    if (ab + bb + hbp + sf) > 0
                    else None
                )
                slg = round(tb / ab, 3) if ab > 0 else None
                ops = round(obp + slg, 3) if obp and slg else None
                stats = {
                    "type": "batting",
                    "G": row["G"],
                    "AB": ab,
                    "AVG": avg,
                    "OBP": obp,
                    "SLG": slg,
                    "OPS": ops,
                    "H": h,
                    "HR": row["HR"],
                    "RBI": row["RBI"],
                    "R": row["R"],
                    "BB": bb,
                    "K": row["K"],
                    "SB": row["SB"],
                    "2B": row["D2"],
                    "3B": row["D3"],
                }

    return {
        "player_id": player_id,
        "first_name": player["first_name"],
        "last_name": player["last_name"],
        "position": player["position"],
        "bats": player["bats"],
        "throws": player["throws"],
        "age": skills.get("age", 0),
        "player_type": grades.player_type,
        "overall": grades.overall,
        "roster_status": status,
        "grades": all_grades,
        "energy": energy,
        "stats": stats,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────


def _gm_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["is_ai"] = bool(d["is_ai"])
    d["is_away"] = bool(d["is_away"])
    return d
