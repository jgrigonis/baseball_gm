# tests/db/repositories/test_player_energy.py
from datetime import date

import pytest

from src.db.repositories.player_energy import (
    PlayerEnergyRepository,
    PlayerEnergyState,
    recover_player_energy,
)


@pytest.fixture
def repo(db_conn):
    return PlayerEnergyRepository(db_conn, league_id="test")


@pytest.fixture
def players(db_conn, factory):
    return factory.player_row(), factory.player_row()


def _state(pid, energy=0.6, last=date(2026, 5, 1), consecutive=3, games=10):
    return PlayerEnergyState(
        player_id=pid,
        current_energy=energy,
        max_energy=0.95,
        last_game_date=last,
        consecutive_days=consecutive,
        season_games_played=games,
    )


def test_get_many_returns_stored_states_only(repo, players):
    p1, p2 = players
    repo.save_player_energy(_state(p1.id))

    states = repo.get_many([p1.id, p2.id])

    assert set(states) == {p1.id}
    assert states[p1.id] == repo.get(p1.id)


def test_get_many_empty_list(repo):
    assert repo.get_many([]) == {}


def test_save_many_upserts_all(repo, players):
    p1, p2 = players
    repo.save_player_energy(_state(p1.id, energy=0.9))

    repo.save_many([_state(p1.id, energy=0.4), _state(p2.id, energy=0.7)])

    assert repo.get(p1.id).current_energy == pytest.approx(0.4)
    assert repo.get(p2.id).current_energy == pytest.approx(0.7)


def test_get_many_with_recovery_matches_single_calls(repo, players):
    p1, p2 = players
    game_date = date(2026, 5, 4)
    repo.save_player_energy(_state(p1.id))
    durabilities = {p2.id: 30, p1.id: 80}

    states = repo.get_many_with_recovery(durabilities, game_date)

    # One entry per requested player, in the order given.
    assert list(states) == [p2.id, p1.id]
    for pid, durability in durabilities.items():
        assert states[pid] == repo.get_with_recovery(pid, game_date, durability)
    assert states[p2.id] == PlayerEnergyState(player_id=p2.id)


def test_recover_player_energy_does_not_modify_input():
    stored = _state("p", energy=0.3)
    recovered = recover_player_energy(stored, "p", date(2026, 5, 4), 50)

    assert recovered.current_energy > 0.3
    assert recovered.consecutive_days == 0
    assert stored == _state("p", energy=0.3)


def test_facilities_speed_position_player_recovery():
    """Better Facilities bring a tired hitter back faster (rate_mult)."""
    stored = _state("p", energy=0.3)
    game_date = date(2026, 5, 4)
    slow = recover_player_energy(stored, "p", game_date, 50, 0.85)
    normal = recover_player_energy(stored, "p", game_date, 50)
    fast = recover_player_energy(stored, "p", game_date, 50, 1.15)

    assert slow.current_energy < normal.current_energy < fast.current_energy
