# tests/league/test_rest_rusty.py
"""Strategy tab Rest rusty players: who a team sits on game day
(src/league/play_season._rested_rusty)."""

from types import SimpleNamespace

from src.league.play_season import (
    REST_RUSTY_MIN_HITTERS,
    REST_RUSTY_MIN_PITCHERS,
    _rested_rusty,
)
from src.team.manager_profile import ManagerProfile


def _team(hitters, pitchers, rest_rusty=True):
    players = [
        SimpleNamespace(id=f"h{i}", pitcher_fatigue=None) for i in range(hitters)
    ]
    players += [
        SimpleNamespace(id=f"p{i}", pitcher_fatigue=object()) for i in range(pitchers)
    ]
    return SimpleNamespace(
        players=players, profile=ManagerProfile(rest_rusty=rest_rusty)
    )


RUST = {"h0": {}, "p0": {}}


def test_off_sits_nobody():
    assert _rested_rusty(_team(13, 13, rest_rusty=False), None, RUST, set()) == set()


def test_on_sits_rusty_hitters_and_pitchers():
    assert _rested_rusty(_team(13, 13), None, RUST, set()) == {"h0", "p0"}


def test_never_leaves_a_side_short():
    team = _team(REST_RUSTY_MIN_HITTERS, REST_RUSTY_MIN_PITCHERS + 1)
    assert _rested_rusty(team, None, RUST, set()) == {"p0"}


def test_only_eligible_and_available_players_count():
    team = _team(13, 13)
    # Injured hitters don't count toward the floor
    hurt = {f"h{i}" for i in range(1, 13 - REST_RUSTY_MIN_HITTERS + 1)}
    assert _rested_rusty(team, None, RUST, hurt) == {"p0"}
    # Nor do players off the active roster
    eligible = [p.id for p in team.players if p.id != "h5"]
    assert _rested_rusty(team, eligible, RUST, set()) == {"h0", "p0"}
