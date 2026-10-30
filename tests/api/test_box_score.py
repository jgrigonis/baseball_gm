"""Box score row order for the game panel (src/api/view_models/box_score.py)."""

from src.api.view_models.box_score import batting_order, in_order, pitching_order


def _lineup(team, *pids):
    return {
        "event_type": "lineup_set",
        "team_id": team,
        "detail_parsed": [
            {"batting_order": i + 1, "player_id": pid} for i, pid in enumerate(pids)
        ],
    }


def _event(kind, team, pid, pid_2=None):
    return {"event_type": kind, "team_id": team, "player_id": pid, "player_id_2": pid_2}


def test_subs_bat_under_the_player_they_replaced():
    events = [
        _lineup("a", "dunn", "bakke", "jackson", "fox"),
        _lineup("h", "dale"),
        _event("substitution", "a", "hively", "jackson"),
        _event("substitution", "a", "smith", "hively"),
    ]

    assert batting_order(events, "a") == [
        "dunn",
        "bakke",
        "jackson",
        "hively",
        "smith",
        "fox",
    ]


def test_pitchers_in_order_of_entry():
    events = [
        _event("pitcher_start", "a", "congo"),
        _event("pitcher_start", "h", "shortes"),
        _event("pitching_change", "a", "swanson", "congo"),
        _event("closer_called", "a", "dedon", "swanson"),
        _event("pitching_change", "a", "webb", "dedon"),
        _event("pitching_change", "a", "dingel", "webb"),
    ]

    assert pitching_order(events, "a") == [
        "congo",
        "swanson",
        "dedon",
        "webb",
        "dingel",
    ]


def test_rows_the_log_misses_keep_their_order_at_the_end():
    rows = [{"player_id": p} for p in ("zed", "bakke", "amos", "dunn")]

    ordered = in_order(rows, ["dunn", "bakke"])

    assert [r["player_id"] for r in ordered] == ["dunn", "bakke", "zed", "amos"]
