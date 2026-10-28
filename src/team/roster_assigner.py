# src/team/roster_assigner.py
"""
Assigns players to roster tiers based on skill ratings.

Tiers:
    26man  — active roster (13 pitchers + 13 position players)
    40man  — extended roster (next best 14)
    minors — everyone else

Uses PlayerEvaluator for position-weighted ratings.
Treats all players as potentially two-way — no hard position filtering.

An AI team can lean young or veteran: bonus adds rating points to players by
id wherever they're ranked (src/league/front_office.py).
"""

from src.player.player_evaluator import PlayerEvaluator
from src.player.player_record import PlayerRecord

# Roster construction constants
MAX_PITCHERS = 13
STARTERS = 5
BULLPEN = MAX_PITCHERS - STARTERS  # 8
LINEUP_POSITIONS = ["c", "1b", "2b", "ss", "3b", "lf", "cf", "rf"]
FLEX_SPOTS = 26 - MAX_PITCHERS - len(LINEUP_POSITIONS)  # 26 - 13 - 8 = 5
FORTY_MAN_PITCHERS = 7
FORTY_MAN_HITTERS = 7  # 40-man = 26 + 14


class RosterAssigner:
    """
    Assigns a pool of players to roster tiers for a single team.

    Usage:
        assigner = RosterAssigner()
        assignments = assigner.assign(players)
        # assignments = {"player_id": "26man" | "40man" | "minors" | "unassigned"}
    """

    def assign(
        self, players: list[PlayerRecord], bonus: dict[str, float] | None = None
    ) -> dict[str, str]:
        """
        Assign all players to roster tiers.

        Args:
            players: Full player pool for a team
            bonus: rating points to add to players, by id, in every ranking

        Returns:
            Dict of player_id -> status string
        """
        assignments = {}
        remaining = list(players)

        # --- Pre-compute ratings for all players once ---
        rated = {p.id: PlayerEvaluator.rate_player(p.skills, p.throws) for p in players}
        if bonus:
            rated = {
                pid: {k: v + bonus.get(pid, 0) for k, v in r.items()}
                for pid, r in rated.items()
            }

        # 1. Pick 5 starters (best sp rating)
        starters = self._pick_top(remaining, rated, "sp", STARTERS)
        for p in starters:
            assignments[p.id] = "26man"
            remaining.remove(p)

        # 2. Pick 8 bullpen (best rp rating, capped so total pitchers <= 13)
        bullpen_slots = MAX_PITCHERS - len(starters)
        bullpen = self._pick_top(remaining, rated, "rp", bullpen_slots)
        for p in bullpen:
            assignments[p.id] = "26man"
            remaining.remove(p)

        # 3. Pick best player per lineup position (offense-weighted)
        for pos in LINEUP_POSITIONS:
            best = self._pick_best_for_position(remaining, rated, pos)
            if best:
                assignments[best.id] = "26man"
                remaining.remove(best)

        # 4. Fill flex spots with best overall_player not yet assigned
        flex = self._pick_top(remaining, rated, "overall_player", FLEX_SPOTS)
        for p in flex:
            assignments[p.id] = "26man"
            remaining.remove(p)

        # 5. Next 7 best pitchers (by p rating) = 40-man
        forty_pitchers = self._pick_top(remaining, rated, "p", FORTY_MAN_PITCHERS)
        for p in forty_pitchers:
            assignments[p.id] = "40man"
            remaining.remove(p)

        # 6. Next 7 best overall hitters = 40-man
        forty_hitters = self._pick_top(
            remaining, rated, "overall_player", FORTY_MAN_HITTERS
        )
        for p in forty_hitters:
            assignments[p.id] = "40man"
            remaining.remove(p)

        # 7. Everyone else = minors
        for p in remaining:
            assignments[p.id] = "minors"

        return assignments

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _pick_top(
        self,
        players: list[PlayerRecord],
        rated: dict[str, dict],
        rating_key: str,
        n: int,
    ) -> list[PlayerRecord]:
        """Return top N players by a single rating key."""
        sorted_players = sorted(
            players,
            key=lambda p: rated[p.id].get(rating_key, 0),
            reverse=True,
        )
        return sorted_players[:n]

    def _pick_best_for_position(
        self,
        players: list[PlayerRecord],
        rated: dict[str, dict],
        pos: str,
    ) -> PlayerRecord | None:
        """
        Return the best player for a position using an offense-weighted score.
        defense 35% / offense 65%
        """
        if not players:
            return None

        def combined_score(p: PlayerRecord) -> int:
            r = rated[p.id]
            defense = r.get(pos, 0)
            offense = r.get("overall_offense", 0)
            return int(defense * 0.35 + offense * 0.65)

        return max(players, key=combined_score)
