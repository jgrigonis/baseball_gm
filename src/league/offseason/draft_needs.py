# src/league/offseason/draft_needs.py
"""
Suggested draft needs: which strategy chips a team's roster calls for.

Position chips (C, IF, OF, SP, RP) come from depth. A player is "usable" at
his best spot (see draft_strategy.group: for a pitcher, his job on the staff,
rotation or bullpen, else the one he rates better at, though a major league
team's starters beyond a 5-man rotation count as relievers) if he rates at least USABLE there and
is no older than MAX_AGE; minor leaguers count half, since many won't make
it. Depth is measured against the league average rather than a fixed target,
since rosters run from 26 players in a new league to 160 later on: below
half the average is High, below 80% of it is Med.

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
HIGH_BELOW = 0.5  # share of the league average depth
MED_BELOW = 0.8

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


def _position_gaps(depth: dict[str, float], average: dict[str, float]) -> list[_Gap]:
    gaps = []
    for chip in POSITIONS:
        if average[chip] <= 0:
            continue
        share = depth[chip] / average[chip]
        if share < MED_BELOW:
            level = HIGH if share < HIGH_BELOW else MED
            reason = f"{depth[chip]:g} usable, league average {average[chip]:.1f}"
            gaps.append(_Gap(chip, level, 1 - share, reason))
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
        gaps = _position_gaps(depths[tid], average)
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
