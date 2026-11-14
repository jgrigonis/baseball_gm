# src/api/schemas.py
#
# Pydantic v2 models for the GM-layer API.
# Raw skill integers → scouting letter grades is handled here, not in the DB.

from __future__ import annotations

import logging
from typing import Literal

from pydantic import BaseModel

from src.api.grade_curves import overall_to_grade, role_to_grade
from src.player.player_evaluator import PlayerEvaluator
from src.player.player_skills import PlayerSkills
from src.player.positions import PITCHER_POSITIONS

log = logging.getLogger(__name__)

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
    (20, "F"),
]


# Experiment: single skills (Contact, Power, Arm, Durability, Stuff...) show
# their 0-100 number instead of a letter. The number keeps its letter's color
# (grade_class / gradeClass) and sorts as before. Set False to go back to
# letters. Overall, role and position grades stay curved letters either way.
SKILLS_AS_NUMBERS = True


def skill_letter(raw: int | None) -> str:
    """The plain-scale letter for a raw 0-100 skill: every 5 points a grade."""
    if raw is None:
        return "?"

    # Ensure input stays in bounds
    score = max(0, min(100, raw))

    # Check against thresholds
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade

    return "F"


def skill_to_grade(raw: int | None) -> str:
    """What a GM sees for a single skill: its number (SKILLS_AS_NUMBERS) or
    its letter."""
    if raw is None:
        return "?"
    if SKILLS_AS_NUMBERS:
        return str(max(0, min(100, int(raw))))
    return skill_letter(raw)


def grade_letter(grade: str | None) -> str:
    """The letter behind a shown grade: a skill number maps to its
    plain-scale letter, a letter stays as it is."""
    g = grade or "?"
    return skill_letter(int(g)) if g.isdigit() else g


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
    player_type follows the listed position; ratings only decide when a
    player has no position (a terrible hitter can rate higher as a pitcher,
    and he is still a hitter).
    """
    throws = player.get("throws", "R") or "R"
    try:
        ps = PlayerSkills(skills)
        ratings = PlayerEvaluator.rate_player(ps, throws)
    except ValueError:
        log.warning("Could not rate player %s", player.get("id"), exc_info=True)
        ratings = {}

    if_rating = max(ratings.get("2b", 0), ratings.get("3b", 0), ratings.get("ss", 0))
    of_rating = max(ratings.get("lf", 0), ratings.get("cf", 0), ratings.get("rf", 0))
    groups = {
        "IF": if_rating,
        "OF": of_rating,
        "CA": ratings.get("c", 0),
        "1B": ratings.get("1b", 0),
    }
    best_field_label = max(groups, key=groups.get) if groups else "IF"
    best_field_val = groups[best_field_label]

    pitcher_overall = max(ratings.get("sp", 0), ratings.get("rp", 0))
    hitter_overall = ratings.get("overall_player", 0)

    position = (player.get("position") or "").lower()
    if position:
        is_pitcher = position in PITCHER_POSITIONS
    else:
        is_pitcher = pitcher_overall > hitter_overall
    raw_overall = pitcher_overall if is_pitcher else hitter_overall

    offense = ratings.get("overall_offense", 0)

    def _skill(key: str) -> str | None:
        val = skills.get(key) or 0
        return skill_to_grade(val) if val > 0 else None

    return PlayerGrades(
        player_id=player["id"],
        first_name=player["first_name"],
        last_name=player["last_name"],
        position=player.get("position"),
        bats=player["bats"],
        throws=player["throws"],
        age=skills.get("age", 0),
        player_type="pitcher" if is_pitcher else "hitter",
        offense=role_to_grade(offense, "overall_offense"),
        overall=overall_to_grade(raw_overall, "pitcher" if is_pitcher else "hitter"),
        # Hitter tools
        contact=_skill("contact"),
        power=_skill("power"),
        eye=_skill("eye"),
        speed=_skill("speed"),
        arm=_skill("arm"),
        field=(
            role_to_grade(best_field_val, "best_def") if best_field_val > 20 else None
        ),
        field_label=best_field_label if best_field_val > 20 else None,
        # Pitcher tools
        stuff=_skill("strikes"),
        control=_skill("accuracy"),
        stamina=_skill("stamina"),
        recovery=_skill("recovery"),
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


# ── Request bodies ───────────────────────────────────────────────
# Unknown fields are ignored (pydantic's default), so these accept every
# payload the dashboard JS sends.


class SimRequest(BaseModel):
    # Game-days to sim, or "season" to sim to the end of the regular season.
    count: int | Literal["season"] = 1


class LineupSlot(BaseModel):
    player_id: str
    batting_order: int
    position: str | None = None


class LineupSaveRequest(BaseModel):
    lineup: list[LineupSlot] = []
    # The opposing starter's hand this lineup is for (R or L).
    vs_hand: Literal["R", "L"] = "R"


class LineupAutofillSlot(BaseModel):
    player_id: str
    position: str | None = None


class LineupAutofillRequest(BaseModel):
    # The lineup on screen, one entry per batting slot (None for empty).
    lineup: list[LineupAutofillSlot | None] = []
    # True starts over; False keeps the players already in the lineup.
    rebuild: bool = False
    # The opposing starter's hand, for the Strategy tab's platoon setting.
    vs_hand: Literal["R", "L"] = "R"
    # A lineup style to build with instead of the Strategy tab's (the Rebuild
    # All menu); None uses the Strategy tab's.
    style: (
        Literal["traditional", "analytics", "speed-first", "power-first", "defensive"]
        | None
    ) = None


class RotationSaveRequest(BaseModel):
    rotation: list[str] = []
    # The pitcher due to start next; falls back to the first slot.
    pointer_pid: str | None = None


class RosterSaveRequest(BaseModel):
    forty_man: list[str] = []
    # Long Form: who of the 40-man is on the active (26-man) roster.
    active: list[str] = []


class InjuredListRequest(BaseModel):
    # Long Form: which injured list, by its days (7, 10, 15 or 60).
    kind: int


class TradeOfferRequest(BaseModel):
    to_team_id: str
    give: list[str] = []  # player ids from the GM's own team
    get: list[str] = []  # player ids from to_team_id
    counter_of: str | None = None  # the offer to the GM this one answers


class TradeShopTakeRequest(BaseModel):
    team_id: str  # the AI team whose shop offer the GM takes


class TradeVoteRequest(BaseModel):
    yes: bool


class DraftPickRequest(BaseModel):
    """A person's pick in the live draft (Long Form)."""

    player_id: str


class DraftScoutsRequest(BaseModel):
    """Leave this pick to the scouts' default, or with rest, every pick
    left."""

    rest: bool = False


class DraftStrategyRequest(BaseModel):
    """Need chips (chip key → level 0-2: Low, Med, High), age preference
    (-1 upside … 1 ready sooner) and pinned player ids. Checked by
    DraftStrategy."""

    chips: dict[str, int] = {}
    age_pref: float = 0.0
    pins: list[str] = []
