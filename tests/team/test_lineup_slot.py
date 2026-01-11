# tests/team/test_lineup_slot.py
"""
What we should test (and nothing more)
1. LineupSlot stores its fields correctly
2. Uses __slots__ (no accidental attributes)
3. Accepts a PlayerInGame
4. Constants are internally consistent and stable
"""

import pytest
from unittest.mock import MagicMock

from src.team.lineup_slot import LineupSlot, LINEUP_SLOTS, POSITION_PRIORITY
from src.player.player_in_game import PlayerInGame


def test_lineup_slot_stores_player_and_position():
    player = MagicMock(spec=PlayerInGame)

    slot = LineupSlot(player=player, position="cf")

    assert slot.player is player
    assert slot.position == "cf"

def test_lineup_slot_is_slotted():
    """This catches accidental attribute creep."""
    slot = LineupSlot(
        player=MagicMock(spec=PlayerInGame),
        position="ss",
    )

    with pytest.raises(AttributeError):
        slot.foo = "bar"

def test_lineup_slots_are_unique():
    assert len(LINEUP_SLOTS) == len(set(LINEUP_SLOTS))

def test_position_priority_is_subset_of_lineup_slots():
    """
    Position priority contains only valid lineup slots
    This is an important invariant — lineup logic depends on it.
    """
    for pos in POSITION_PRIORITY:
        assert pos in LINEUP_SLOTS

def test_position_priority_has_no_duplicates():
    assert len(POSITION_PRIORITY) == len(set(POSITION_PRIORITY))

