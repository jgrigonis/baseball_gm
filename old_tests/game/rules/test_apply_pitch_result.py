import pytest

from src.game.rules.pitch_result import apply_pitch_result
from src.game.count import Count


@pytest.mark.parametrize(
    "initial_balls,initial_strikes,result,ends_pa,expected_outcome",
    [
        # -----------------------
        # Balls
        # -----------------------
        (0, 0, "ball", False, None),
        (3, 0, "ball", True, "walk"),
        # -----------------------
        # Strikes
        # -----------------------
        (0, 0, "strike", False, None),
        (0, 2, "strike", True, "strikeout"),
        # -----------------------
        # Fouls
        # -----------------------
        (0, 0, "foul", False, None),
        (0, 1, "foul", False, None),
        (0, 2, "foul", False, None),  # no reset, no strike added
        # -----------------------
        # Foul tips
        # -----------------------
        (0, 1, "foul_tip", False, None),
        (0, 2, "foul_tip", True, "strikeout"),
        # -----------------------
        # Hit by pitch
        # -----------------------
        (0, 0, "hit_by_pitch", True, "hit_by_pitch"),
        # -----------------------
        # Ball in play
        # -----------------------
        (0, 0, "in_play", True, "in_play"),
    ],
)
def test_apply_pitch_result(
    initial_balls,
    initial_strikes,
    result,
    ends_pa,
    expected_outcome,
):
    count = Count()
    count.balls = initial_balls
    count.strikes = initial_strikes

    outcome = apply_pitch_result(count, result)

    if ends_pa:
        assert outcome is not None
        assert outcome.type == expected_outcome
        assert count.balls == 0
        assert count.strikes == 0
    else:
        assert outcome is None
