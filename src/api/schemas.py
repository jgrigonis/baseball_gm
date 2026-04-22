# src/api/schemas.py
#
# Pydantic v2 models for the GM-layer API.
# Raw skill integers → scouting letter grades is handled here, not in the DB.

from __future__ import annotations

# from datetime import datetime
from typing import Literal

from pydantic import BaseModel

# ── Scouting grades ───────────────────────────────────────────────────────────
# The sim engine stores skills as integers (roughly 0-100).
# GMs see A+-F letter grades; raw numbers are debug-only.

# 0-100 version
_GRADE_THRESHOLDS: list[tuple[int, str]] = [
    (80, "A+"),
    (75, "A"),
    (70, "A-"),
    (65, "B+"),
    (60, "B"),
    (55, "B-"),
    (50, "C+"),
    (45, "C"),
    (40, "C-"),
    (35, "D+"),
    (30, "D"),
    (25, "D-"),
]


def skill_to_grade(raw: int | None) -> str:
    """Map a raw 0-100 skill integer directly to letter grades."""
    if raw is None:
        return "?"

    # Ensure input stays in bounds
    score = max(0, min(100, raw))

    # Check against thresholds
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade

    return "F"


# scaled useless version
# def skill_to_grade(raw: int | None) -> str:
#     """Map a raw 0-100 skill integer to the A+-F scouting letter grade."""
#     if raw is None:
#         return "?"
#     scaled = round(20 + (max(0, min(100, raw)) / 100) * 60)
#     for threshold, grade in _GRADE_THRESHOLDS:
#         if scaled >= threshold:
#             return grade
#     return "F"

# ── Player / roster ───────────────────────────────────────────────────────────


class PlayerGrades(BaseModel):
    """Scouting grades shown to a GM. Raw integers are never exposed."""

    player_id: str
    first_name: str
    last_name: str
    position: str | None
    bats: str
    throws: str
    age: int
    player_type: Literal["hitter", "pitcher"]

    # Hitter tools (None when pitcher)
    contact: str | None = None
    power: str | None = None
    eye: str | None = None
    speed: str | None = None
    arm: str | None = None
    field: str | None = None  # best defensive grade (infield/outfield/catching)
    field_label: str | None = None  # "CA", "IF", or "OF"
    offense: str | None = None
    overall: str

    # Pitcher tools (None when hitter)
    stuff: str | None = None
    control: str | None = None
    stamina: str | None = None
    recovery: str | None = None

    roster_status: str  # '26man' | '40man' | 'minors' | etc.


def player_row_to_grades(player: dict, skills: dict, status: str) -> PlayerGrades:
    """
    Build a PlayerGrades from raw dicts.
    Determines player_type from whether pitching skills dominate.
    """
    # A player is treated as a pitcher if they have meaningful stamina/strikes
    is_pitcher = (skills.get("stamina", 0) or 0) > 20 and (
        skills.get("strikes", 0) or 0
    ) > 20

    catching = skills.get("catching", 0) or 0
    infield = skills.get("infield", 0) or 0
    outfield = skills.get("outfield", 0) or 0

    best_field_val = max(catching, infield, outfield)
    if best_field_val == catching:
        best_field_label = "CA"
    elif best_field_val == infield:
        best_field_label = "IF"
    else:
        best_field_label = "OF"

    # TODO these are not done the same way as the skill ratings
    if is_pitcher:
        # Overall for pitchers: weighted blend of stuff, control, stamina
        raw_overall = round(
            (skills.get("strikes", 50) or 50) * 0.25
            + (skills.get("accuracy", 50) or 50) * 0.20
            + (skills.get("stamina", 50) or 50) * 0.20
            + (skills.get("recovery", 50) or 50) * 0.15
            + (skills.get("ground_balls", 50) or 50) * 0.20
        )

    else:
        raw_overall = round(
            (skills.get("contact", 50) or 50) * 0.25
            + (skills.get("power", 50) or 50) * 0.20
            + (skills.get("eye", 50) or 50) * 0.20
            + (skills.get("speed", 50) or 50) * 0.15
            + best_field_val * 0.20
        )
    offense = round(
        (skills.get("contact", 50) or 50) * 0.30
        + (skills.get("power", 50) or 50) * 0.25
        + (skills.get("eye", 50) or 50) * 0.25
        + (skills.get("speed", 50) or 50) * 0.20
    )
    # raw_overall = expand_distribution(raw_overall)

    return PlayerGrades(
        player_id=player["id"],
        first_name=player["first_name"],
        last_name=player["last_name"],
        position=player.get("position"),
        bats=player["bats"],
        throws=player["throws"],
        age=skills.get("age", 0),
        player_type="pitcher" if is_pitcher else "hitter",
        offense=skill_to_grade(offense),
        overall=skill_to_grade(raw_overall),
        # Hitter tools
        contact=skill_to_grade(skills.get("contact")) if not is_pitcher else None,
        power=skill_to_grade(skills.get("power")) if not is_pitcher else None,
        eye=skill_to_grade(skills.get("eye")) if not is_pitcher else None,
        speed=skill_to_grade(skills.get("speed")) if not is_pitcher else None,
        arm=skill_to_grade(skills.get("arm")) if not is_pitcher else None,
        field=skill_to_grade(best_field_val) if not is_pitcher else None,
        field_label=best_field_label if not is_pitcher else None,
        # Pitcher tools
        stuff=skill_to_grade(skills.get("strikes")) if is_pitcher else None,
        control=skill_to_grade(skills.get("accuracy")) if is_pitcher else None,
        stamina=skill_to_grade(skills.get("stamina")) if is_pitcher else None,
        recovery=skill_to_grade(skills.get("recovery")) if is_pitcher else None,
        roster_status=status,
    )


# Currently unused.
def expand_distribution(value: float, factor: float = 1.28) -> int:
    """
    This will stretch good players to be overall rated higher, and
    poor players to rate lower.
    """
    # 1. Normalize to -1.0 to 1.0
    normalized = (value - 50) / 50
    # 2. Apply power while preserving the sign (+/-)
    sign = 1 if normalized >= 0 else -1
    stretched = sign * (abs(normalized) ** (1 / factor))
    # 3. Scale back to 0-100
    return round((stretched * 50) + 50)


# ── Bullpen ──────────────────────────────────────────────────────


class BullpenSaveRequest(BaseModel):
    bullpen: dict[str, str]  # Matches {"player_id": "role"}
