# tests/api/test_lineup_rotation_size.py
#
# The Lineup tab's rotation Auto-fill and Rebuild pick the Strategy tab's
# playoff rotation size during the playoffs.

import pytest

from src.api.view_models.lineup import auto_rotation_size
from src.team.manager_profile import ManagerProfile


@pytest.mark.parametrize(
    "rotation_size, playoff_rotation, state, expected",
    [
        (5, "4", "playoffs", 4),
        (5, "3", "playoffs", 3),
        (6, "same", "playoffs", 6),
        (5, "3", "season", 5),
        (4, "3", "preseason", 4),
        (5, "4", "", 5),
    ],
)
def test_auto_rotation_size(rotation_size, playoff_rotation, state, expected):
    profile = ManagerProfile(
        rotation_size=rotation_size, playoff_rotation=playoff_rotation
    )
    assert auto_rotation_size(profile, state) == expected
