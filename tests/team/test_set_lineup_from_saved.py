# tests/team/test_set_lineup_from_saved.py
"""
tests/team/test_set_lineup_from_saved.py

Unit tests for TeamInGame._set_lineup_from_saved.

Run with:
    python -m pytest tests/team/test_set_lineup_from_saved.py -v
"""

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Minimal stubs so we don't need the full game stack
# ---------------------------------------------------------------------------

def make_player(pid, ratings=None, is_injured=False):
    """Create a minimal PlayerInGame-like mock."""
    p = MagicMock()
    p.id = pid
    p.record.id = pid
    p.is_injured = is_injured
    p.ratings = ratings or {}
    p.pitcher_fatigue = None  # position player
    # apply_fatigue_to_ratings is a no-op
    p.apply_fatigue_to_ratings = MagicMock()
    p.is_rated.return_value = True
    return p


def make_lineup_slot(player, position):
    from src.team.lineup_slot import LineupSlot
    return LineupSlot(player, position)


def make_team(players, pitcher=None):
    """Build a minimal TeamInGame with controlled players."""
    from src.team.team_in_game import TeamInGame
    from src.team.lineup_optimizer import LineupOptimizer

    record = MagicMock()
    record.players = []  # not used in _set_lineup_from_saved directly

    team = TeamInGame.__new__(TeamInGame)
    team.record = record
    team.players = players
    team.pitcher = pitcher
    team.lineup = []
    team._positions = {}
    team.batter_index = 0
    team.logger = MagicMock()
    team._optimizer = LineupOptimizer.optimize
    return team


# ---------------------------------------------------------------------------
# Helper: build saved_lineup dicts
# ---------------------------------------------------------------------------

def saved_slot(pid, batting_order, position):
    return {"player_id": pid, "batting_order": batting_order, "position": position}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSetLineupFromSaved:

    def test_all_healthy_uses_saved_order(self):
        """All 9 players healthy — lineup matches saved order exactly."""
        players = [make_player(f"p{i}") for i in range(1, 10)]
        pitcher = make_player("pitcher")
        team = make_team(players + [pitcher], pitcher=pitcher)

        saved = [saved_slot(f"p{i}", i, "dh") for i in range(1, 10)]
        available = players  # pitcher excluded by _set_lineup_from_saved

        team._set_lineup_from_saved(saved, available, "prioritized", dh=True)

        assert len(team.lineup) == 9
        pids = [s.player.id for s in team.lineup]
        assert pids == [f"p{i}" for i in range(1, 10)]

    def test_no_duplicate_players(self):
        """No player appears twice in the lineup regardless of injuries."""
        # 9 position players, 4 injured (slots 1,2,6,8)
        healthy = [make_player(f"h{i}") for i in range(1, 6)]  # 5 healthy non-saved
        injured = [make_player(f"inj{i}", is_injured=True) for i in range(1, 5)]
        all_players = healthy + injured
        pitcher = make_player("pitcher")
        team = make_team(all_players + [pitcher], pitcher=pitcher)

        # Saved lineup: 9 slots, 4 are injured players
        saved = [
            saved_slot("inj1", 1, "c"),
            saved_slot("inj2", 2, "ss"),
            saved_slot("h1",   3, "3b"),
            saved_slot("h2",   4, "lf"),
            saved_slot("h3",   5, "cf"),
            saved_slot("inj3", 6, "1b"),
            saved_slot("h4",   7, "rf"),
            saved_slot("inj4", 8, "2b"),
            saved_slot("h5",   9, "dh"),
        ]
        available = healthy  # only healthy players available

        team._set_lineup_from_saved(saved, available, "prioritized", dh=True)

        pids = [s.player.id for s in team.lineup]
        assert len(pids) == len(set(pids)), f"Duplicate players: {pids}"

    def test_injured_player_gets_sub(self):
        """An injured player in the saved lineup gets a substitute."""
        healthy = make_player("sub", ratings={"c": 80})
        injured = make_player("inj", is_injured=True)
        pitcher = make_player("pitcher")
        team = make_team([healthy, injured, pitcher], pitcher=pitcher)

        saved = [
            saved_slot("inj", 1, "c"),
            saved_slot("sub", 2, "1b"),  # sub is healthy at slot 2
        ]
        # Only healthy player available
        available = [healthy]

        # 7 more players needed to fill 9 slots — gap-fill will need more players
        # For this test just verify no crash and sub appears
        extra = [make_player(f"e{i}") for i in range(7)]
        available = [healthy] + extra
        team.players = [healthy, injured, pitcher] + extra

        team._set_lineup_from_saved(saved, available, "prioritized", dh=True)

        pids = [s.player.id for s in team.lineup]
        assert "inj" not in pids, "Injured player should not be in lineup"
        assert len(pids) == len(set(pids)), f"Duplicate players: {pids}"

    def test_sub_used_as_sub_not_duplicated_at_original_slot(self):
        """
        Critical: if player A is chosen as sub for injured slot 1,
        and player A also appears in saved slot 6, they must NOT appear twice.
        """
        player_a = make_player("A", ratings={"c": 99})  # best catcher, also in slot 6
        injured  = make_player("inj", is_injured=True)
        others   = [make_player(f"o{i}") for i in range(7)]
        pitcher  = make_player("pitcher")
        all_players = [player_a, injured] + others + [pitcher]
        team = make_team(all_players, pitcher=pitcher)

        saved = [
            saved_slot("inj", 1, "c"),   # injured — A will be chosen as sub
            saved_slot("o0",  2, "ss"),
            saved_slot("o1",  3, "3b"),
            saved_slot("o2",  4, "lf"),
            saved_slot("o3",  5, "cf"),
            saved_slot("A",   6, "1b"),  # A's original slot — must NOT be added again
            saved_slot("o4",  7, "rf"),
            saved_slot("o5",  8, "2b"),
            saved_slot("o6",  9, "dh"),
        ]
        available = [player_a] + others

        team._set_lineup_from_saved(saved, available, "prioritized", dh=True)

        pids = [s.player.id for s in team.lineup]
        assert pids.count("A") == 1, f"Player A appears {pids.count('A')} times"
        assert len(pids) == len(set(pids)), f"Duplicates: {pids}"

    def test_four_injuries_still_produces_nine_players(self):
        """4 injured position players — lineup is still filled to 9."""
        injured = [make_player(f"inj{i}", is_injured=True) for i in range(4)]
        healthy = [make_player(f"h{i}",   ratings={"dh": 50}) for i in range(9)]
        pitcher = make_player("pitcher")
        team = make_team(injured + healthy + [pitcher], pitcher=pitcher)

        saved = [
            saved_slot("inj0", 1, "c"),
            saved_slot("inj1", 2, "ss"),
            saved_slot("h0",   3, "3b"),
            saved_slot("h1",   4, "lf"),
            saved_slot("h2",   5, "cf"),
            saved_slot("inj2", 6, "1b"),
            saved_slot("h3",   7, "rf"),
            saved_slot("inj3", 8, "2b"),
            saved_slot("h4",   9, "dh"),
        ]
        available = healthy

        team._set_lineup_from_saved(saved, available, "prioritized", dh=True)

        pids = [s.player.id for s in team.lineup]
        assert len(pids) == 9, f"Expected 9 players, got {len(pids)}: {pids}"
        assert len(pids) == len(set(pids)), f"Duplicates: {pids}"
        for pid in [f"inj{i}" for i in range(4)]:
            assert pid not in pids, f"Injured player {pid} in lineup"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
