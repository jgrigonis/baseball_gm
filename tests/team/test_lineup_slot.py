# tests/team/test_lineup_slot.py
"""
What we should test (and nothing more)
1. LineupSlot stores its fields correctly
2. Uses __slots__ (no accidental attributes)
3. Accepts a PlayerInGame
"""

import pytest
from unittest.mock import MagicMock

from src.team.lineup_slot import LineupSlot
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
