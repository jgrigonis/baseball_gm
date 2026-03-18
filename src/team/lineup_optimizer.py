"""
Players + Rules + Strategy
        ↓
Optimized Lineup (LineupSlot[])

The optimizer should be:
Stateless
Deterministic
Pure (no mutation, no randomness)
Rating-driven (consumes player.ratings)
Strategy-based (offense / defense / balanced / prioritized)
Reusable (TeamInGame, AI manager, simulations)

It should:
Choose batting order
Assign defensive positions
Respect DH rules
Never mutate PlayerInGame

It does not:
load teams
rate players
track innings
know game state

Returns:
lineup → ordered list of LineupSlot
pitcher → chosen starting pitcher
"""

from src.team.lineup_slot import LineupSlot, LINEUP_SLOTS, POSITION_PRIORITY
from src.player.player_evaluator import LEFT_HAND_CAPPED_POSITIONS
from src.player.player_in_game import PlayerInGame


class LineupOptimizer:
    @staticmethod
    def optimize(
        players: list[PlayerInGame],
        *,
        style: str = "prioritized",
        dh: bool = True,
        pitcher: PlayerInGame | None = None,
    ) -> tuple[list[LineupSlot], PlayerInGame]:
        # Defensive guard — filter out any injured players that slipped through
        players = [p for p in players if not p.is_injured]
        if pitcher is None:
            pitcher = LineupOptimizer.select_pitcher(players)
        if dh:
            hitters = [p for p in players if p != pitcher]
        else:
            hitters = players.copy()
        # hitters = [p for p in players if p != pitcher or dh]
        if style == "defensive":
            lineup = LineupOptimizer.defensive_lineup(hitters, pitcher, dh)
        elif style == "offensive":
            lineup = LineupOptimizer.offensive_lineup(hitters, pitcher, dh)
        elif style == "prioritized":
            lineup = LineupOptimizer.prioritized_lineup(hitters, pitcher, dh)
        elif style == "balanced":
            lineup = LineupOptimizer.balanced_lineup(hitters, pitcher, dh)
        else:
            raise ValueError(f"Unknown lineup style: {style}")

        return lineup, pitcher

    @staticmethod
    def select_pitcher(players: list[PlayerInGame]) -> PlayerInGame:
        return max(players, key=lambda p: (p.ratings.get("p", 0), p.record.id))

    @staticmethod
    def prioritized_lineup(hitters, pitcher, dh):
        """
        Offensive batting order + priority-based defensive assignment.
        Batting order never changes after selection.
        """

        # 1. Build batting order
        order = LineupOptimizer.offensive_batting_order(hitters, dh=dh)

        # 2. Assign defensive positions by priority
        assignments = LineupOptimizer.assign_positions_priority(
            order, dh=dh, pitcher=pitcher
        )

        # 3. Build lineup slots (batting order preserved)
        return LineupOptimizer.build_lineup(order, assignments)

    @staticmethod
    def balanced_lineup(hitters, pitcher, dh):
        """
        Pick the best overall players, assign a balanced batting order,
        then greedily assign defensive positions.
        """
        # --- select hitters ---
        sorted_hitters = sorted(
            hitters,
            key=lambda p: (p.ratings.get("overall_player", 0), p.record.id),
            reverse=True,
        )

        count = 9 if dh else 8
        lineup_players = sorted_hitters[:count]

        pool = lineup_players.copy()

        # --- batting order ---
        leadoff = max(pool, key=lambda p: (p.ratings.get("lead_off", 0), p.record.id))
        pool.remove(leadoff)

        two = max(pool, key=lambda p: (p.ratings.get("contact_hitter", 0), p.record.id))
        pool.remove(two)

        three = max(
            pool, key=lambda p: (p.ratings.get("overall_offense", 0), p.record.id)
        )
        pool.remove(three)

        cleanup = max(
            pool, key=lambda p: (p.ratings.get("power_hitter", 0), p.record.id)
        )
        pool.remove(cleanup)

        five = max(
            pool, key=lambda p: (p.ratings.get("overall_offense", 0), p.record.id)
        )
        pool.remove(five)

        six = max(pool, key=lambda p: (p.ratings.get("overall_player", 0), p.record.id))
        pool.remove(six)

        seven = max(
            pool, key=lambda p: (p.ratings.get("overall_player", 0), p.record.id)
        )
        pool.remove(seven)

        eight = max(
            pool, key=lambda p: (p.ratings.get("overall_player", 0), p.record.id)
        )
        pool.remove(eight)

        order = [leadoff, two, three, cleanup, five, six, seven, eight]

        if dh:
            nine = max(
                pool, key=lambda p: (p.ratings.get("speed_runner", 0), p.record.id)
            )
            order.append(nine)

        # --- defensive assignment ---
        assignments = LineupOptimizer.assign_positions_greedy(
            order, dh=dh, pitcher=pitcher
        )

        return LineupOptimizer.build_lineup(order, assignments)

    @staticmethod
    def balanceded_lineup(hitters, pitcher, dh):
        """
        Pick the 8 or 9 best overall_players and first assign
        the batting order, then greedily assign them to defense
        """

        # 1. Build batting order
        order = LineupOptimizer.offensive_batting_order(hitters, dh=dh)

        # 2. Assign defensive positions by priority
        assignments = LineupOptimizer.assign_positions_priority(
            order, dh=dh, pitcher=pitcher
        )

        # 3. Build lineup slots (batting order preserved)
        return LineupOptimizer.build_lineup(order, assignments)

    @staticmethod
    def offensive_lineup(hitters, pitcher, dh):
        """
        Offensive batting order + greedily assigned defensive positions.
        Batting order never changes after selection.
        """

        # 1. Build batting order
        order = LineupOptimizer.offensive_batting_order(hitters, dh=dh)

        # 2. Assign defensive positions by priority
        assignments = LineupOptimizer.assign_positions_greedy(
            order, dh=dh, pitcher=pitcher
        )

        # 3. Build lineup slots (batting order preserved)
        return LineupOptimizer.build_lineup(order, assignments)

    @staticmethod
    def defensive_lineup(hitters, pitcher, dh):
        """
        This will automatically put together a defensive lineup,
        it will greedily pick the best player aavailable at each
        position, in the order of priority set in the LINEUP_SLOTS.
        """

        # 1. Assign defensive positions by priority
        assignments = LineupOptimizer.assign_positions_greedy(
            hitters, dh=dh, pitcher=pitcher
        )

        # 2. Build batting order
        order = LineupOptimizer.offensive_batting_order(assignments, dh=dh)

        # 3. Build lineup slots (batting order preserved)
        return LineupOptimizer.build_lineup(order, assignments)

    @staticmethod
    def offensive_batting_order(hitters, *, dh):
        if len(hitters) < (9 if dh else 8):
            raise ValueError(f"Not enough hitters to build lineup: {len(hitters)}")
        hitters = hitters.copy()

        leadoff = max(
            hitters, key=lambda p: (p.ratings.get("lead_off", 0), p.record.id)
        )
        hitters.remove(leadoff)

        two = max(
            hitters, key=lambda p: (p.ratings.get("contact_hitter", 0), p.record.id)
        )
        hitters.remove(two)

        three = max(
            hitters, key=lambda p: (p.ratings.get("overall_offense", 0), p.record.id)
        )
        hitters.remove(three)

        cleanup = max(
            hitters, key=lambda p: (p.ratings.get("power_hitter", 0), p.record.id)
        )
        hitters.remove(cleanup)

        five = max(
            hitters, key=lambda p: (p.ratings.get("power_hitter", 0), p.record.id)
        )
        hitters.remove(five)

        six = max(
            hitters, key=lambda p: (p.ratings.get("overall_offense", 0), p.record.id)
        )
        hitters.remove(six)

        seven = max(
            hitters, key=lambda p: (p.ratings.get("overall_offense", 0), p.record.id)
        )
        hitters.remove(seven)

        eight = max(
            hitters, key=lambda p: (p.ratings.get("overall_offense", 0), p.record.id)
        )
        hitters.remove(eight)

        if dh:
            nine = max(
                hitters, key=lambda p: (p.ratings.get("speed_runner", 0), p.record.id)
            )
        else:
            nine = None

        order = [leadoff, two, three, cleanup, five, six, seven, eight]
        if nine:
            order.append(nine)

        return order

    @staticmethod
    def assign_positions_greedy(players, *, dh, pitcher=None):
        remaining_players = set(players)
        positions = list(LINEUP_SLOTS)
        if dh:
            positions.append("dh")
        elif pitcher:
            remaining_players.discard(pitcher)  # pitcher handled separately
        else:
            positions.append("p")

        assignments = {}

        while remaining_players and positions:
            best = None
            for player in remaining_players:
                for pos in positions:
                    score = player.ratings.get(pos, 0)
                    if best is None or score > best[0]:
                        best = (score, player, pos)

            _, player, pos = best
            assignments[player] = pos
            remaining_players.remove(player)
            positions.remove(pos)

        for p in remaining_players:
            assignments[p] = "bench"

        if pitcher and not dh:
            assignments[pitcher] = "p"

        return assignments

    @staticmethod
    def assign_positions_priority(players, *, dh, pitcher=None):
        priority = list(POSITION_PRIORITY)
        if not dh:
            if pitcher is None:
                priority.insert(0, "p")

        remaining = set(players)
        if pitcher and not dh:
            remaining.discard(pitcher)

        assignments = {}

        for pos in priority:
            if not remaining:
                break

            candidates = remaining
            if pos in LEFT_HAND_CAPPED_POSITIONS:
                righty_candidates = {
                    p for p in remaining if (p.throws or "R").upper() != "L"
                }
                if righty_candidates:  # only filter if righties are available
                    candidates = righty_candidates
            best = max(candidates, key=lambda p: (p.ratings.get(pos, 0), p.record.id))
            assignments[best] = pos
            remaining.remove(best)

        for p in remaining:
            assignments[p] = "dh"

        if pitcher and not dh:
            assignments[pitcher] = "p"

        return assignments

    @staticmethod
    def build_lineup(order, assignments):
        return [LineupSlot(p, assignments[p]) for p in order]
