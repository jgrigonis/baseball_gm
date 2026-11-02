"""
Players + Strategy
        ↓
Optimized Lineup (LineupSlot[])

The optimizer is stateless, deterministic and pure: it reads player.ratings
and player.skills and never mutates a player. It's used for AI teams before
every game, to fill holes in a person's saved lineup, and by the Lineup tab's
Auto-fill and Rebuild buttons (plans/ai-gm-strategy.md, section 3).

It works in two steps:

1. Who plays where, solved exactly as an assignment problem with the
   Hungarian algorithm (scipy's linear_sum_assignment). A matrix of every hitter against every spot on the field
   (and DH). A cell is what that player is worth there:

       value = overall_offense + DEFENSE_IMPORTANCE[pos] × rating at pos

   DH is all bat. Defense counts most up the middle, so the solve fills C, SS
   and CF well without a hard-coded order, and a big bat with no glove ends up
   at 1B or DH. A left-handed thrower is only put at C, 2B, SS or 3B when
   nobody else can play there.

2. Batting order. The chosen hitters fill the batting slots top-down: slot 1
   takes whoever best fits its role in the lineup style (BATTING_ROLES), then
   slot 2 takes the best fit of who's left, and so on. Slot 1 is always
   LEADOFF, the same formula as the player card's Leadoff grade, so the best
   Leadoff grade in the lineup leads off. Slots with no special role go by
   overall bat, so better hitters bat higher.

Locked players (a person's partly filled lineup) keep their batting slot and
position; only the gaps are solved.

Platoons (section 5): given the hand of the starter the lineup faces, a hitter
who bats from the same side loses PLATOON_PENALTY points of offense, in both
steps. The platoon setting decides whether that's used: "none" ignores
the starter, "vs-handedness" gives today's everyday lineup a REGULAR_BONUS so
only a close bench player takes a regular's spot, and "aggressive" plays the
best matchup lineup.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment

from src.player.player_evaluator import LEFT_HAND_CAPPED_POSITIONS, ROLE_WEIGHTS
from src.player.player_in_game import PlayerInGame
from src.team.lineup_slot import LineupSlot

FIELD_POSITIONS = ["c", "1b", "2b", "3b", "ss", "lf", "cf", "rf"]

# How much a point of glove is worth against a point of bat, by position.
DEFENSE_IMPORTANCE = {
    "c": 1.0,
    "ss": 1.0,
    "cf": 0.9,
    "2b": 0.8,
    "3b": 0.7,
    "rf": 0.6,
    "lf": 0.5,
    "1b": 0.4,
}

# Keeps a lefty thrower off C/2B/SS/3B unless there's no one else.
LEFTY_PENALTY = 1000
# Makes sure a locked player with no position still plays.
MUST_PLAY_BONUS = 10000
# Stands in for "can't happen" in the assignment matrix.
IMPOSSIBLE = -1e9

# Rating points of offense a same-side hitter (RvR, LvL) loses. Measured in
# the sim (modify_for_platoon in src/game/modifiers/): same-side hitters lose
# about .025 of wOBA, and a point of overall_offense is worth about .0036.
# Switch hitters never lose any.
PLATOON_PENALTY = 7.0
# Under "vs-handedness", how much a bench player's matchup must beat a
# regular's by to take his spot.
REGULAR_BONUS = 3.0
PLATOON_SETTINGS = ("none", "vs-handedness", "aggressive")

# The role each batting slot plays in a lineup style, as weights on hitting
# skills. Slots with no special role use OVERALL and are sorted by bat alone.
OVERALL = {"contact": 3, "power": 3, "eye": 2, "speed": 1}
POWER = {"power": 4, "contact": 1, "clutch": 1}
# Every style leads off with an on-base hitter: the card's Leadoff grade.
LEADOFF = ROLE_WEIGHTS["lead_off"]

BATTING_ROLES: dict[str, list[dict[str, int]]] = {
    # On-base at the top, the best hitter third, power fourth and fifth.
    "traditional": [
        LEADOFF,
        {"contact": 3, "bunting": 1, "speed": 1},
        {"contact": 3, "power": 3, "eye": 2},
        POWER,
        {"power": 3, "contact": 1},
        OVERALL,
        OVERALL,
        OVERALL,
        OVERALL,
    ],
    # The Book: on-base first, the best hitter second, a second leadoff
    # sixth and a wrap-around ninth.
    "analytics": [
        LEADOFF,
        OVERALL,
        {"contact": 3, "eye": 2, "power": 1},
        {"power": 4, "contact": 2, "clutch": 1},
        POWER,
        {"eye": 2, "speed": 2, "contact": 1},
        OVERALL,
        OVERALL,
        {"speed": 2, "eye": 2, "contact": 1},
    ],
    "speed-first": [
        LEADOFF,
        {"speed": 2, "contact": 2, "base_running": 1},
        OVERALL,
        POWER,
        {"contact": 2, "eye": 1},
        {"speed": 2, "contact": 1},
        OVERALL,
        OVERALL,
        {"speed": 2, "eye": 1},
    ],
    "power-first": [
        LEADOFF,
        OVERALL,
        {"power": 3, "contact": 1},
        POWER,
        POWER,
        OVERALL,
        OVERALL,
        OVERALL,
        OVERALL,
    ],
}
LINEUP_STYLES = tuple(BATTING_ROLES)
DEFAULT_STYLE = "analytics"


class LineupOptimizer:
    @staticmethod
    def optimize(
        players: list[PlayerInGame],
        *,
        style: str = DEFAULT_STYLE,
        dh: bool = True,
        pitcher: PlayerInGame | None = None,
        vs_hand: str | None = None,
        platoon: str = "none",
        form: dict[str, float] | None = None,
        defense: float = 1.0,
    ) -> tuple[list[LineupSlot], PlayerInGame]:
        """The best lineup from these players. Picks a pitcher if none is
        given; he doesn't bat with a DH."""
        if style not in BATTING_ROLES:
            raise ValueError(f"Unknown lineup style: {style}")
        players = [p for p in players if not p.is_injured]
        if pitcher is None:
            pitcher = LineupOptimizer.select_pitcher(players)
        hitters = [p for p in players if p is not pitcher]
        lineup = LineupOptimizer.fill(
            [None] * 9,
            hitters,
            style=style,
            dh=dh,
            vs_hand=vs_hand,
            platoon=platoon,
            form=form,
            defense=defense,
        )
        return lineup, pitcher

    @staticmethod
    def select_pitcher(players: list[PlayerInGame]) -> PlayerInGame:
        return max(players, key=lambda p: (p.ratings.get("p", 0), p.record.id))

    @staticmethod
    def fill(
        locked: list[tuple[PlayerInGame, str | None] | None],
        hitters: list[PlayerInGame],
        *,
        style: str = DEFAULT_STYLE,
        dh: bool = True,
        vs_hand: str | None = None,
        platoon: str = "none",
        form: dict[str, float] | None = None,
        defense: float = 1.0,
    ) -> list[LineupSlot]:
        """Fill the empty slots of a lineup.

        locked has one entry per batting slot: (player, position) to keep, or
        None for a slot to fill. A locked player with no position keeps his
        slot and gets the best open position. hitters is everyone eligible to
        play; locked players may be in it or not. Rebuild is fill() with
        every slot None. vs_hand is the throwing hand of the opposing starter
        (R or L), used as the platoon setting says. form adds to a hitter's
        offense (by player id): how his season stats look to this GM
        (src/league/performance.py). defense multiplies how much a glove
        counts: above 1 for a glove-first GM, below for a bat-first one.
        """
        size = 9 if dh else 8
        positions = FIELD_POSITIONS + (["dh"] if dh else [])
        locked = (list(locked) + [None] * size)[:size]

        fixed: dict[int, tuple[PlayerInGame, str]] = {}
        must_play: dict[int, PlayerInGame] = {}
        taken_positions: set[str] = set()
        taken_ids: set[str] = set()
        for i, entry in enumerate(locked):
            if entry is None:
                continue
            player, pos = entry
            if player.record.id in taken_ids:
                continue
            taken_ids.add(player.record.id)
            if pos in positions and pos not in taken_positions:
                fixed[i] = (player, pos)
                taken_positions.add(pos)
            else:
                must_play[i] = player

        open_positions = [pos for pos in positions if pos not in taken_positions]
        pool = list(must_play.values()) + sorted(
            (p for p in hitters if p.record.id not in taken_ids),
            key=lambda p: p.record.id,
        )
        if len(pool) < len(open_positions):
            raise ValueError(
                f"Not enough hitters to build lineup: need {len(open_positions)},"
                f" have {len(pool)}"
            )

        # Step 1: who plays where.
        hand = vs_hand if platoon in ("vs-handedness", "aggressive") else None
        form = form or {}
        bonus: dict[str, float] = dict(form)
        if hand and platoon == "vs-handedness":
            everyday = LineupOptimizer.assign_positions(
                pool,
                open_positions,
                must_play=set(must_play.values()),
                bonus=form,
                defense=defense,
            )
            for p, _ in everyday:
                bonus[p.record.id] = bonus.get(p.record.id, 0) + REGULAR_BONUS
        chosen = LineupOptimizer.assign_positions(
            pool,
            open_positions,
            must_play=set(must_play.values()),
            vs_hand=hand,
            bonus=bonus,
            defense=defense,
        )

        # Step 2: the new players' batting slots. Locked-without-position
        # players keep their slot.
        by_slot: dict[int, LineupSlot] = {
            i: LineupSlot(p, pos) for i, (p, pos) in fixed.items()
        }
        position_of = {p.record.id: pos for p, pos in chosen}
        for i, p in must_play.items():
            by_slot[i] = LineupSlot(p, position_of[p.record.id])
        newcomers = [(p, pos) for p, pos in chosen if p.record.id not in taken_ids]
        open_slots = [i for i in range(size) if i not in by_slot]
        for i, (p, pos) in zip(
            open_slots,
            LineupOptimizer.batting_order(newcomers, open_slots, style, hand),
        ):
            by_slot[i] = LineupSlot(p, pos)

        return [by_slot[i] for i in range(size)]

    @staticmethod
    def matchup(player: PlayerInGame, vs_hand: str | None) -> float:
        """The offense a hitter loses against a starter who throws with this
        hand: none unless he bats from the same side."""
        if vs_hand and (player.bats or "R").upper() == vs_hand.upper():
            return PLATOON_PENALTY
        return 0.0

    @staticmethod
    def position_value(
        player: PlayerInGame,
        pos: str,
        vs_hand: str | None = None,
        defense: float = 1.0,
    ) -> float:
        """What a player is worth at a spot: his bat (against today's starter,
        if given), plus his glove there weighted by how much defense matters
        at that spot (times defense, the GM's taste)."""
        offense = player.ratings.get("overall_offense", 0)
        offense -= LineupOptimizer.matchup(player, vs_hand)
        if pos == "dh":
            return offense
        value = offense + defense * DEFENSE_IMPORTANCE[pos] * player.ratings.get(pos, 0)
        if pos in LEFT_HAND_CAPPED_POSITIONS and (player.throws or "R").upper() == "L":
            value -= LEFTY_PENALTY
        return value

    @staticmethod
    def assign_positions(
        players: list[PlayerInGame],
        positions: list[str],
        must_play: set[PlayerInGame] = frozenset(),
        vs_hand: str | None = None,
        bonus: dict[str, float] | None = None,
        defense: float = 1.0,
    ) -> list[tuple[PlayerInGame, str]]:
        """The best player at each position, all chosen together. bonus adds
        to a player's value everywhere (by player id). Returns (player,
        position) for each position."""
        bonus = bonus or {}
        if not positions:
            return []
        value = np.array(
            [
                [
                    LineupOptimizer.position_value(p, pos, vs_hand, defense)
                    + bonus.get(p.record.id, 0)
                    + (MUST_PLAY_BONUS if p in must_play else 0)
                    for pos in positions
                ]
                for p in players
            ]
        )
        rows, cols = linear_sum_assignment(value, maximize=True)
        picked = sorted(zip(rows, cols), key=lambda rc: rc[1])
        return [(players[r], positions[c]) for r, c in picked]

    @staticmethod
    def slot_fit(player: PlayerInGame, role: dict[str, int]) -> float:
        """How well a hitter fits a batting role, 0-100."""
        skills = player.skills
        return sum(skills.get(k, 0) * w for k, w in role.items()) / sum(role.values())

    @staticmethod
    def batting_order(
        players: list[tuple[PlayerInGame, str]],
        slots: list[int],
        style: str,
        vs_hand: str | None = None,
    ) -> list[tuple[PlayerInGame, str]]:
        """Order players into these batting slots (0-based), top-down: each
        slot in turn takes the best fit for its role among those left,
        against today's starter if given. Returns them in slot order."""
        roles = BATTING_ROLES[style]
        left = sorted(players, key=lambda pp: pp[0].record.id)
        order = []
        for s in sorted(slots)[: len(left)]:
            best = max(
                left,
                key=lambda pp: (
                    LineupOptimizer.slot_fit(pp[0], roles[s])
                    - LineupOptimizer.matchup(pp[0], vs_hand)
                ),
            )
            left.remove(best)
            order.append(best)
        return order
