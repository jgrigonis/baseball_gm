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

# Fixed version
# _GRADE_THRESHOLDS: list[tuple[int, str]] = [
#     (73, "A+"),
#     (69, "A"),
#     (65, "A-"),
#     (61, "B+"),
#     (57, "B"),
#     (53, "B-"),
#     (49, "C+"),
#     (45, "C"),
#     (41, "C-"),
#     (37, "D+"),
#     (33, "D"),
#     (29, "D-"),
#     (25, "F"),
# ]

# testing version
# _GRADE_THRESHOLDS: list[tuple[int, str]] = [
#     (67, "A+"),
#     (64, "A"),
#     (61, "A-"),
#     (58, "B+"),
#     (55, "B"),
#     (52, "B-"),
#     (49, "C+"),
#     (46, "C"),
#     (43, "C-"),
#     (40, "D+"),
#     (37, "D"),
#     (34, "D-"),
#     (31, "F"),
# ]

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


# ── League ────────────────────────────────────────────────────────────────────


# class LeagueCreate(BaseModel):
#     name: str = Field(..., min_length=1, max_length=60)
#     mode: Literal["blitz", "longform"] = "blitz"
#     num_teams: int = Field(30, ge=2, le=30)
#     decision_window_sec: int = Field(120, ge=30, le=600)
#     reentry_enabled: bool = True
#     pace_control: Literal["timer", "confirmed", "scheduled"] = "timer"
#     commissioner_display_name: str = Field(..., min_length=1, max_length=40)


# class LeagueResponse(BaseModel):
#     id: str
#     name: str
#     join_code: str
#     mode: str
#     num_teams: int
#     decision_window_sec: int
#     reentry_enabled: bool
#     pace_control: str
#     state: str
#     commissioner_gm_id: str | None
#     created_at: str

#     model_config = {"from_attributes": True}


# class LeagueJoin(BaseModel):
#     display_name: str = Field(..., min_length=1, max_length=40)


# ── GM ────────────────────────────────────────────────────────────────────────


# class GMResponse(BaseModel):
#     id: str
#     league_id: str
#     team_id: str | None
#     display_name: str
#     is_ai: bool
#     is_away: bool
#     career_seasons: int
#     warned_at: str | None
#     fired_at: str | None
#     # session token returned only on creation
#     user_session: str | None = None

#     model_config = {"from_attributes": True}


# class GMAwayUpdate(BaseModel):
#     is_away: bool


# ── Strategic profile ─────────────────────────────────────────────────────────

# LineupStyle = Literal["traditional", "analytics", "speed-first", "power-first"]
# StealAggression = Literal["conservative", "standard", "aggressive"]
# SacBunt = Literal["never", "situational", "frequent"]
# StarterUsage = Literal["let-them-work", "pitch-count-strict", "matchup-based"]
# CloserUsage = Literal["saves-only", "high-leverage", "best-available"]
# BullpenPref = Literal["deep-pen", "starter-heavy"]
# PlatoonUsage = Literal["none", "vs-handedness", "aggressive"]


# class GMProfileResponse(BaseModel):
#     gm_id: str
#     lineup_style: str
#     steal_aggression: str
#     sac_bunt: str
#     starter_usage: str
#     closer_usage: str
#     bullpen_pref: str
#     dh_enabled: bool
#     platoon_usage: str
#     updated_at: str

#     model_config = {"from_attributes": True}


# class GMProfileUpdate(BaseModel):
#     """All fields optional — patch semantics."""

#     lineup_style: LineupStyle | None = None
#     steal_aggression: StealAggression | None = None
#     sac_bunt: SacBunt | None = None
#     starter_usage: StarterUsage | None = None
#     closer_usage: CloserUsage | None = None
#     bullpen_pref: BullpenPref | None = None
#     dh_enabled: bool | None = None
#     platoon_usage: PlatoonUsage | None = None

#     @model_validator(mode="after")
#     def at_least_one_field(self) -> "GMProfileUpdate":
#         if all(v is None for v in self.model_dump().values()):
#             raise ValueError("At least one profile field must be provided.")
#         return self


# ── Draft ─────────────────────────────────────────────────────────────────────


# class DraftResponse(BaseModel):
#     id: str
#     league_id: str
#     season_id: str
#     format: str
#     state: str
#     current_pick: int
#     pick_timer_sec: int
#     created_at: str


# class DraftPickResponse(BaseModel):
#     pick_number: int
#     round: int
#     gm_id: str
#     team_id: str
#     player_id: str
#     auto_picked: bool
#     picked_at: str


# class PreferenceListSubmit(BaseModel):
#     """Ordered list of player IDs, highest preference first."""

#     player_ids: list[str] = Field(..., min_length=1)


# class PreferenceListResponse(BaseModel):
#     gm_id: str
#     draft_id: str
#     preferences: list[str]  # player_ids in rank order


# ── GM season evaluation ──────────────────────────────────────────────────────


# class GMEvaluationResponse(BaseModel):
#     gm_id: str
#     season_id: str
#     wins: int
#     losses: int
#     expected_wins: float | None
#     roster_quality_rating: float | None
#     made_playoffs: bool
#     won_championship: bool
#     verdict: str | None
#     evaluated_at: str
