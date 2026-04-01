# tests/db/repositories/test_pitcher_state.py
import sqlite3
from datetime import date, timedelta

import pytest

from src.db.repositories.pitcher_state import (
    PitcherStateRepository,
    PitcherState,
    _daily_recovery_rate,
    _apply_recovery,
    availability_weight,
    MIN_ENERGY_STARTER,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def conn():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        """
        CREATE TABLE pitcher_state (
            player_id TEXT,
            league_id TEXT,
            current_energy REAL,
            max_energy REAL,
            last_game_date TEXT,
            last_pitch_count INTEGER,
            consecutive_days INTEGER,
            PRIMARY KEY (player_id, league_id)
        )
        """
    )
    return conn


@pytest.fixture
def repo(conn):
    return PitcherStateRepository(conn, league_id="test")


# ---------------------------------------------------------------------------
# Recovery math tests
# ---------------------------------------------------------------------------

def test_daily_recovery_rate_bounds():
    low = _daily_recovery_rate(1)
    mid = _daily_recovery_rate(50)
    high = _daily_recovery_rate(100)

    assert low < mid < high
    assert 0 < low < 1
    assert 0 < high < 1


def test_apply_recovery_increases_energy():
    energy = 0.2
    recovered = _apply_recovery(energy, days=3, recovery_skill=50)

    assert recovered > energy
    assert recovered <= 1.0


def test_apply_recovery_caps_at_1():
    recovered = _apply_recovery(0.99, days=10, recovery_skill=100)
    assert recovered <= 1.0


# ---------------------------------------------------------------------------
# Availability logic
# ---------------------------------------------------------------------------

def test_availability_full_rest():
    state = PitcherState(
        player_id="p1",
        current_energy=0.5,
        max_energy=1.0,
        last_game_date=date.today() - timedelta(days=5),
        last_pitch_count=80,
    )

    assert availability_weight(state, date.today()) == 1.0


def test_availability_partial_rest():
    state = PitcherState(
        player_id="p1",
        current_energy=0.5,
        max_energy=1.0,
        last_game_date=date.today() - timedelta(days=1),
        last_pitch_count=80,  # needs 4 days
    )

    weight = availability_weight(state, date.today())
    assert 0.05 <= weight < 1.0


def test_availability_min_floor():
    state = PitcherState(
        player_id="p1",
        current_energy=0.5,
        max_energy=1.0,
        last_game_date=date.today(),
        last_pitch_count=100,
    )

    assert availability_weight(state, date.today()) >= 0.05


# ---------------------------------------------------------------------------
# Repository: get / save
# ---------------------------------------------------------------------------

def test_save_and_get(repo):
    state = PitcherState(
        player_id="p1",
        current_energy=0.5,
        max_energy=1.0,
        last_game_date=date(2026, 1, 1),
        last_pitch_count=50,
        consecutive_days=2,
    )

    repo.save(state)
    loaded = repo.get("p1")

    assert loaded is not None
    assert loaded.player_id == "p1"
    assert loaded.current_energy == pytest.approx(0.5)
    assert loaded.last_pitch_count == 50
    assert loaded.consecutive_days == 2


def test_get_missing_returns_none(repo):
    assert repo.get("nope") is None


# ---------------------------------------------------------------------------
# get_with_recovery
# ---------------------------------------------------------------------------

def test_get_with_recovery_no_history(repo):
    state = repo.get_with_recovery("p1", date.today())

    assert state.current_energy == 1.0
    assert state.max_energy == 1.0


def test_get_with_recovery_applies_rest(repo):
    game_date = date(2026, 1, 10)

    repo.save(
        PitcherState(
            player_id="p1",
            current_energy=0.2,
            max_energy=1.0,
            last_game_date=game_date - timedelta(days=3),
            last_pitch_count=50,
        )
    )

    state = repo.get_with_recovery("p1", game_date, recovery_skill=50)

    assert state.current_energy > 0.2
    assert state.current_energy <= state.max_energy


def test_get_with_recovery_negative_days(repo):
    game_date = date(2026, 1, 10)

    repo.save(
        PitcherState(
            player_id="p1",
            current_energy=0.2,
            max_energy=1.0,
            last_game_date=game_date + timedelta(days=1),
        )
    )

    state = repo.get_with_recovery("p1", game_date)

    assert state.current_energy == 1.0  # fallback


# ---------------------------------------------------------------------------
# get_available_pitchers
# ---------------------------------------------------------------------------

def test_get_available_pitchers(repo):
    today = date.today()

    repo.save(
        PitcherState(
            player_id="p1",
            current_energy=0.9,
            max_energy=1.0,
            last_game_date=today - timedelta(days=3),
        )
    )

    repo.save(
        PitcherState(
            player_id="p2",
            current_energy=0.2,
            max_energy=1.0,
            last_game_date=today,
        )
    )

    available = repo.get_available_pitchers(
        ["p1", "p2"], today, min_energy=MIN_ENERGY_STARTER
    )

    ids = {p.player_id for p in available}
    assert "p1" in ids
    assert "p2" not in ids


# ---------------------------------------------------------------------------
# update_after_game
# ---------------------------------------------------------------------------

def test_update_after_game_inserts(repo):
    today = date.today()

    repo.update_after_game(
        player_id="p1",
        final_energy=0.4,
        max_energy=1.0,
        pitch_count=50,
        game_date=today,
    )

    state = repo.get("p1")
    assert state is not None
    assert state.last_pitch_count == 50
    assert state.consecutive_days == 1


def test_update_after_game_no_pitch_noop(repo):
    today = date.today()

    repo.update_after_game(
        player_id="p1",
        final_energy=0.4,
        max_energy=1.0,
        pitch_count=0,
        game_date=today,
    )

    assert repo.get("p1") is None


def test_update_after_game_consecutive_days(repo):
    today = date.today()

    repo.save(
        PitcherState(
            player_id="p1",
            current_energy=0.5,
            max_energy=1.0,
            last_game_date=today - timedelta(days=1),
            consecutive_days=2,
        )
    )

    repo.update_after_game(
        player_id="p1",
        final_energy=0.3,
        max_energy=1.0,
        pitch_count=30,
        game_date=today,
    )

    state = repo.get("p1")
    assert state.consecutive_days == 3


# ---------------------------------------------------------------------------
# delete / clear
# ---------------------------------------------------------------------------

def test_delete(repo):
    repo.save(PitcherState("p1", 0.5, 1.0))

    assert repo.delete("p1") is True
    assert repo.get("p1") is None


def test_clear_all(repo):
    repo.save(PitcherState("p1", 0.5, 1.0))
    repo.save(PitcherState("p2", 0.5, 1.0))

    deleted = repo.clear_all()
    assert deleted == 2
    assert repo.get("p1") is None
    assert repo.get("p2") is None
