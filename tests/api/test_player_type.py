"""player_type follows the listed position, not whichever rating is higher."""

from src.api.schemas import player_row_to_grades

# Leo Hawkins, an 18-year-old DH whose ratings are bad enough that his
# pitching rates higher than his hitting.
AWFUL = {
    "age": 18,
    "strikes": 7,
    "accuracy": 7,
    "stamina": 8,
    "recovery": 5,
    "ground_balls": 11,
    "clutch": 91,
    "durability": 9,
    "contact": 23,
    "power": 22,
    "eye": 41,
    "speed": 3,
    "base_running": 17,
    "bunting": 44,
    "catching": 20,
    "infield": 20,
    "outfield": 20,
    "arm": 12,
}


def _row(position):
    return {
        "id": "p1",
        "first_name": "Leo",
        "last_name": "Hawkins",
        "position": position,
        "bats": "switch",
        "throws": "R",
    }


def test_hitter_position_wins_over_ratings():
    assert player_row_to_grades(_row("dh"), AWFUL, "free_agent").player_type == "hitter"
    assert player_row_to_grades(_row("DH"), AWFUL, "free_agent").player_type == "hitter"


def test_pitcher_position_is_a_pitcher():
    for pos in ("sp", "rp", "p"):
        assert (
            player_row_to_grades(_row(pos), AWFUL, "free_agent").player_type
            == "pitcher"
        )


def test_no_position_falls_back_to_ratings():
    grades = player_row_to_grades(_row(None), AWFUL, "free_agent")
    assert grades.player_type in ("pitcher", "hitter")
