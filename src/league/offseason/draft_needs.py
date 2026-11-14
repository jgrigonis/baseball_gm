# src/league/offseason/draft_needs.py
"""
Suggested draft needs: which strategy chips a team's roster calls for.

Position chips (C, IF, OF, SP, RP) come from two things (Josh, 2026-11-14):

- The 26-man starter's grade at each spot, on the same curves the player
  panel shows (grade_curves.role_to_grade). Hitters are placed at the eight
  fielding spots best first; a chip goes by its weakest starter (IF covers
  1B, 2B, 3B and SS; OF the three outfield spots). SP goes by the average of
  the top ROTATION starters, RP by the top BULLPEN relievers. Below C is
  Med, below D is High.
- Depth in the organization against fixed targets (DEPTH_TARGETS), never
  more than the league has on average, since rosters run from 26 players in
  a new league to 160 later on. A player is "usable" at his best spot (see
  draft_strategy.group: for a pitcher, his job on the staff, rotation or
  bullpen, else the one he rates better at, though a major league team's
  starters beyond a 5-man rotation count as relievers) if he rates at least
  USABLE there and is no older than MAX_AGE; minor leaguers count half,
  since many won't make it. Below the target is Med, below half of it High.

Player-type chips come from comparing the team with the rest of the league:
the team's top 9 hitters (by Overall Offense) are averaged on each hitting
rating, its top 5 starters on SP and top 5 relievers on RP. A team in the
bottom quarter of the league gets that chip at Med. The hitting ratings move
together, so only the worst of them is suggested.

At most MAX_CHIPS chips are suggested, the biggest gaps first, so the
suggestion steers without taking over. AI GMs draft with the same needs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.api.grade_curves import GRADES, role_to_grade
from src.league.offseason.draft_strategy import (
    CHIPS,
    HIGH,
    MED,
    DraftStrategy,
    group,
    ratings,
    staff_groups,
)
from src.player.player_record import PlayerRecord

USABLE = 55  # B-
MAX_AGE = 31
MINORS_WEIGHT = 0.5
POSITIONS = ("c", "if", "of", "sp", "rp")
HIGH_BELOW = 0.5  # share of the depth target
MED_BELOW = 1.0
# Usable players a team should have at each spot, organization-wide.
DEPTH_TARGETS = {"c": 2, "if": 4, "of": 4, "sp": 6, "rp": 7}
# A starter graded below these is a need.
MED_GRADE_BELOW = "C"
HIGH_GRADE_BELOW = "D"
# The fielding spots each chip covers, and the staff sizes judged.
SPOTS = {"c": ("c",), "if": ("1b", "2b", "3b", "ss"), "of": ("lf", "cf", "rf")}
ROTATION = 5
BULLPEN = 7

TOP_HITTERS = 9
TOP_PITCHERS = 5
BOTTOM_SHARE = 0.25
MIN_TEAMS = 4  # too few teams to rank against below this
# Overall Offense first, so it wins a tie: a lineup weak at everything needs
# offense, not one kind of hitter.
HITTER_TYPES = ("offense", "lead_off", "contact", "power", "speed")
MAX_CHIPS = 3

MAJORS = ("26man", "40man")

type Rated = list[tuple[PlayerRecord, str, dict[str, int], str]]  # …, group


@dataclass
class TeamNeeds:
    chips: dict[str, int] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)

    def strategy(self) -> DraftStrategy:
        return DraftStrategy(chips=dict(self.chips))


@dataclass
class _Gap:
    chip: str
    level: int
    severity: float  # bigger is a worse gap
    reason: str


def _depth(roster: Rated) -> dict[str, float]:
    depth = dict.fromkeys(POSITIONS, 0.0)
    for p, status, r, g in roster:
        if g in depth and r[g] >= USABLE and p.age <= MAX_AGE:
            depth[g] += 1.0 if status in MAJORS else MINORS_WEIGHT
    return depth


def _below(grade: str, cut: str) -> bool:
    return grade in GRADES and GRADES.index(grade) > GRADES.index(cut)


def _starter_grades(roster: Rated) -> dict[str, tuple[str, str]]:
    """{chip: (grade, what)} for the 26-man's starters: the weakest at each
    chip's fielding spots, and the rotation's and bullpen's average."""
    active = [(p, r, g) for p, status, r, g in roster if status == "26man"]
    if not active:
        return {}  # no big league roster yet: nothing to judge
    hitters = [(p, r) for p, r, _ in active if not p.is_pitcher()]
    # The eight spots, filled best fit first, one spot a player.
    spots = [s for chip in SPOTS.values() for s in chip]
    pairs = sorted(((r[s], p.id, s) for p, r in hitters for s in spots), reverse=True)
    starters: dict[str, float] = {}
    used: set[str] = set()
    for rating, pid, spot in pairs:
        if spot in starters or pid in used:
            continue
        starters[spot] = rating
        used.add(pid)
    out = {}
    for chip, chip_spots in SPOTS.items():
        worst = min(((starters.get(s, 0.0), s) for s in chip_spots), key=lambda x: x[0])
        grade = role_to_grade(worst[0], worst[1])
        what = "Starting catcher" if chip == "c" else f"Starter at {worst[1].upper()}"
        out[chip] = (grade, what)
    for chip, size, what in (("sp", ROTATION, "Rotation"), ("rp", BULLPEN, "Bullpen")):
        vals = sorted(
            (r[chip] for p, r, g in active if p.is_pitcher() and g == chip),
            reverse=True,
        )[:size]
        vals += [0.0] * (size - len(vals))
        out[chip] = (role_to_grade(sum(vals) / size, chip), what)
    return out


def _position_gaps(
    depth: dict[str, float],
    average: dict[str, float],
    starters: dict[str, tuple[str, str]],
) -> list[_Gap]:
    gaps = []
    for chip in POSITIONS:
        found = []
        grade, what = starters.get(chip, ("?", ""))
        if _below(grade, HIGH_GRADE_BELOW):
            found.append(_Gap(chip, HIGH, 1.5, f"{what} grades {grade}"))
        elif _below(grade, MED_GRADE_BELOW):
            found.append(_Gap(chip, MED, 0.9, f"{what} grades {grade}"))
        # The fixed target, or the league's (rounded) average if that's less.
        target = min(DEPTH_TARGETS[chip], round(average[chip]))
        if target > 0:
            share = depth[chip] / target
            if share < MED_BELOW:
                level = HIGH if share < HIGH_BELOW else MED
                reason = (
                    f"{depth[chip]:g} usable, target {target}"
                    f" (league average {average[chip]:.1f})"
                )
                found.append(
                    _Gap(chip, level, 1 - share + (0.5 if level == HIGH else 0), reason)
                )
        if found:
            gaps.append(max(found, key=lambda g: (g.level, g.severity)))
    return gaps


def _type_scores(roster: Rated) -> dict[str, float]:
    """The team's average on each player-type chip's rating, from its major
    league roster."""
    majors = [(p, r, g) for p, status, r, g in roster if status in MAJORS]
    hitters = sorted(
        ((p, r) for p, r, _ in majors if not p.is_pitcher()),
        key=lambda x: x[1]["overall_offense"],
        reverse=True,
    )[:TOP_HITTERS]
    scores = {}
    for chip in HITTER_TYPES:
        vals = [r[CHIPS[chip].rating] for _, r in hitters]
        scores[chip] = sum(vals) / len(vals) if vals else 0.0
    for chip, role in (("ace_sp", "sp"), ("relief_ace", "rp")):
        vals = sorted(
            (r[role] for p, r, g in majors if p.is_pitcher() and g == role),
            reverse=True,
        )[:TOP_PITCHERS]
        scores[chip] = sum(vals) / len(vals) if vals else 0.0
    return scores


def league_needs(
    rosters: dict[str, list[tuple[PlayerRecord, str]]],
    staff: dict[str, str] | None = None,
) -> dict[str, TeamNeeds]:
    """{team_id: TeamNeeds} for every team, given each team's players and
    their statuses (26man, 40man, minors…), and `staff`: {player_id: sp|rp}
    for the pitchers in a rotation or bullpen."""
    staff = staff or {}
    rated: dict[str, Rated] = {}
    for tid, players in rosters.items():
        rs = [(p, status, ratings(p)) for p, status in players]
        majors = staff_groups(
            [(p, r) for p, status, r in rs if status in MAJORS and p.is_pitcher()],
            staff,
        )
        rated[tid] = [
            (p, status, r, majors.get(p.id) or group(p, r, staff.get(p.id)))
            for p, status, r in rs
        ]
    depths = {tid: _depth(roster) for tid, roster in rated.items()}
    type_scores = {tid: _type_scores(roster) for tid, roster in rated.items()}
    n_teams = len(rated)
    average = {
        chip: sum(d[chip] for d in depths.values()) / max(n_teams, 1)
        for chip in POSITIONS
    }

    needs = {}
    for tid in rated:
        gaps = _position_gaps(depths[tid], average, _starter_grades(rated[tid]))
        type_gaps = []
        for chip, mine in type_scores[tid].items():
            # Place among the league: 1 = best, n_teams = worst
            place = 1 + sum(1 for s in type_scores.values() if s[chip] > mine)
            if n_teams >= MIN_TEAMS and place > n_teams * (1 - BOTTOM_SHARE):
                reason = f"{_ordinal(place)} of {n_teams} in the league"
                type_gaps.append(_Gap(chip, MED, 0.5 * place / n_teams, reason))
        hitting = [g for g in type_gaps if g.chip in HITTER_TYPES]
        if hitting:
            gaps.append(max(hitting, key=lambda g: g.severity))
        gaps += [g for g in type_gaps if g.chip not in HITTER_TYPES]
        gaps.sort(key=lambda g: g.severity, reverse=True)
        chosen = gaps[:MAX_CHIPS]
        needs[tid] = TeamNeeds(
            chips={g.chip: g.level for g in chosen},
            reasons={g.chip: g.reason for g in chosen},
        )
    return needs


def _ordinal(n: int) -> str:
    suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    if 10 <= n % 100 <= 20:
        suffix = "th"
    return f"{n}{suffix}"
