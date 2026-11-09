"""The Rusty badge hover spells out which ratings are down (rust_view)."""

from src.api.view_models.player_cards import rust_view


def test_single_rating_spelled_out():
    r = rust_view({"skills": {"stamina": 3.2}, "days_left": 4})
    assert r == {"text": "ST −3", "tip": "Stamina (ST) is down 3.", "days": 4}


def test_several_ratings_joined_biggest_first():
    r = rust_view({"skills": {"strikes": 3, "stamina": 5, "arm": 4}, "days_left": 9})
    assert r["text"] == "ST −5 · AR −4 · KK −3"
    assert r["tip"] == (
        "Stamina (ST) is down 5, Arm (AR) is down 4 and Stuff (KK) is down 3."
    )


def test_hitter_ratings_and_underscores():
    r = rust_view({"skills": {"base_running": 2, "speed": 4}, "days_left": 2})
    assert r["tip"] == "Speed (SP) is down 4 and Base running (BR) is down 2."


def test_nothing_left_is_none():
    assert rust_view(None) is None
    assert rust_view({"skills": {"speed": 0.3}, "days_left": 1}) is None


def test_accuracy_reads_as_control():
    r = rust_view({"skills": {"accuracy": 3}, "days_left": 2})
    assert r["tip"] == "Control (AC) is down 3."
