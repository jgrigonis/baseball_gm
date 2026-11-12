# tests/db/repositories/test_pitcher_state.py
from datetime import date, timedelta
import pytest

from src.db.repositories.pitcher_state import (
    PitcherStateRepository,
    PitcherState,
    _daily_recovery_rate,
    _apply_recovery,
    availability_weight,
    recover_pitcher_state,
    MIN_ENERGY_STARTER,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def repo(db_conn):
    return PitcherStateRepository(db_conn, league_id="test")


@pytest.fixture
def players(db_conn, factory):
    """Two unique players per test — no cross-test ID collisions."""
    p1 = factory.player_row()
    p2 = factory.player_row()
    return p1, p2


# ---------------------------------------------------------------------------
# Recovery math tests  (pure — no DB needed)
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
        player_id="any",
        current_energy=0.5,
        max_energy=1.0,
        last_game_date=date.today() - timedelta(days=5),
        last_pitch_count=80,
    )
    assert availability_weight(state, date.today()) == 1.0


def test_availability_partial_rest():
    state = PitcherState(
        player_id="any",
        current_energy=0.5,
        max_energy=1.0,
        last_game_date=date.today() - timedelta(days=1),
        last_pitch_count=80,
    )
    weight = availability_weight(state, date.today())
    assert 0.05 <= weight < 1.0


def test_availability_min_floor():
    state = PitcherState(
        player_id="any",
        current_energy=0.5,
        max_energy=1.0,
        last_game_date=date.today(),
        last_pitch_count=100,
    )
    assert availability_weight(state, date.today()) >= 0.05


# ---------------------------------------------------------------------------
# Repository: get / save
# ---------------------------------------------------------------------------


def test_save_and_get(repo, players):
    p1, _ = players
    state = PitcherState(
        player_id=p1.id,
        current_energy=0.5,
        max_energy=1.0,
        last_game_date=date(2026, 1, 1),
        last_pitch_count=50,
        consecutive_days=2,
    )
    repo.save_pitcher_state(state)
    loaded = repo.get(p1.id)

    assert loaded is not None
    assert loaded.player_id == p1.id
    assert loaded.current_energy == pytest.approx(0.5)
    assert loaded.last_pitch_count == 50
    assert loaded.consecutive_days == 2


def test_get_missing_returns_none(repo):
    assert repo.get("nope") is None


# ---------------------------------------------------------------------------
# get_with_recovery
# ---------------------------------------------------------------------------


def test_get_with_recovery_no_history(repo, players):
    p1, _ = players
    state = repo.get_with_recovery(p1.id, date.today())
    assert state.current_energy == 1.0
    assert state.max_energy == 1.0


def test_get_with_recovery_applies_rest(repo, players):
    p1, _ = players
    game_date = date(2026, 1, 10)
    repo.save_pitcher_state(
        PitcherState(
            player_id=p1.id,
            current_energy=0.2,
            max_energy=1.0,
            last_game_date=game_date - timedelta(days=3),
            last_pitch_count=50,
        )
    )

    state = repo.get_with_recovery(p1.id, game_date, recovery_skill=50)
    assert state.current_energy > 0.2
    assert state.current_energy <= state.max_energy


def test_get_with_recovery_negative_days(repo, players):
    p1, _ = players
    game_date = date(2026, 1, 10)
    repo.save_pitcher_state(
        PitcherState(
            player_id=p1.id,
            current_energy=0.2,
            max_energy=1.0,
            last_game_date=game_date + timedelta(days=1),
        )
    )

    state = repo.get_with_recovery(p1.id, game_date)
    assert state.current_energy == 0.2


# ---------------------------------------------------------------------------
# get_available_pitchers
# ---------------------------------------------------------------------------


def test_get_available_pitchers(repo, players):
    p1, p2 = players
    today = date.today()

    repo.save_pitcher_state(
        PitcherState(
            player_id=p1.id,
            current_energy=0.9,
            max_energy=1.0,
            last_game_date=today - timedelta(days=3),
        )
    )
    repo.save_pitcher_state(
        PitcherState(
            player_id=p2.id,
            current_energy=0.2,
            max_energy=1.0,
            last_game_date=today,
        )
    )

    available = repo.get_available_pitchers(
        [p1.id, p2.id], today, min_energy=MIN_ENERGY_STARTER
    )

    ids = {p.player_id for p in available}
    assert p1.id in ids
    assert p2.id not in ids


# ---------------------------------------------------------------------------
# update_after_game
# ---------------------------------------------------------------------------


def test_update_after_game_inserts(repo, players):
    p1, _ = players
    today = date.today()

    repo.update_after_game(
        player_id=p1.id,
        final_energy=0.4,
        max_energy=1.0,
        pitch_count=50,
        game_date=today,
    )

    state = repo.get(p1.id)
    assert state is not None
    assert state.last_pitch_count == 50
    assert state.consecutive_days == 1


def test_update_after_game_no_pitch_noop(repo, players):
    p1, _ = players
    today = date.today()

    repo.update_after_game(
        player_id=p1.id,
        final_energy=0.4,
        max_energy=1.0,
        pitch_count=0,
        game_date=today,
    )

    assert repo.get(p1.id) is None


def test_update_after_game_consecutive_days(repo, players):
    p1, _ = players
    today = date.today()

    repo.save_pitcher_state(
        PitcherState(
            player_id=p1.id,
            current_energy=0.5,
            max_energy=1.0,
            last_game_date=today - timedelta(days=1),
            consecutive_days=2,
        )
    )

    repo.update_after_game(
        player_id=p1.id,
        final_energy=0.3,
        max_energy=1.0,
        pitch_count=30,
        game_date=today,
    )

    state = repo.get(p1.id)
    assert state.consecutive_days == 3


# ---------------------------------------------------------------------------
# Batch methods
# ---------------------------------------------------------------------------


def test_get_many_returns_stored_states_only(repo, players):
    p1, p2 = players
    repo.save_pitcher_state(PitcherState(p1.id, 0.5, 0.9, date(2026, 1, 1), 40, 2))

    states = repo.get_many([p1.id, p2.id])

    assert set(states) == {p1.id}
    assert states[p1.id] == repo.get(p1.id)


def test_get_many_empty_list(repo):
    assert repo.get_many([]) == {}


def test_save_many_upserts_all(repo, players):
    p1, p2 = players
    repo.save_pitcher_state(PitcherState(p1.id, 0.9, 1.0))

    repo.save_many(
        [
            PitcherState(p1.id, 0.3, 0.95, date(2026, 1, 2), 80, 1),
            PitcherState(p2.id, 0.6, 1.0, date(2026, 1, 2), 20, 1),
        ]
    )

    assert repo.get(p1.id).current_energy == pytest.approx(0.3)
    assert repo.get(p1.id).last_pitch_count == 80
    assert repo.get(p2.id).current_energy == pytest.approx(0.6)


def test_update_many_after_game_matches_single_updates(repo, players):
    p1, p2 = players
    today = date(2026, 5, 2)
    repo.save_pitcher_state(
        PitcherState(p1.id, 0.5, 1.0, today - timedelta(days=1), 20, 2)
    )

    repo.update_many_after_game(
        [(p1.id, 0.3, 0.98, 25), (p2.id, 0.4, 1.0, 90)],
        today,
    )

    s1, s2 = repo.get(p1.id), repo.get(p2.id)
    assert s1.consecutive_days == 3
    assert s1.current_energy == pytest.approx(0.3)
    assert s1.max_energy == pytest.approx(0.98)
    assert s2.consecutive_days == 1
    assert s2.last_pitch_count == 90
    assert s2.last_game_date == today


def test_update_many_after_game_skips_zero_pitches(repo, players):
    p1, p2 = players
    repo.update_many_after_game(
        [(p1.id, 0.3, 1.0, 0), (p2.id, 0.4, 1.0, 30)], date(2026, 5, 2)
    )
    assert repo.get(p1.id) is None
    assert repo.get(p2.id) is not None


def test_recover_pitcher_state_does_not_modify_input():
    stored = PitcherState("p", 0.2, 0.9, date(2026, 5, 1), 90, 3)
    recovered = recover_pitcher_state(stored, "p", date(2026, 5, 6), 50)

    assert recovered.current_energy > 0.2
    assert recovered.consecutive_days == 0
    assert stored == PitcherState("p", 0.2, 0.9, date(2026, 5, 1), 90, 3)


def test_recover_pitcher_state_matches_get_with_recovery(repo, players):
    p1, _ = players
    game_date = date(2026, 5, 6)
    repo.save_pitcher_state(PitcherState(p1.id, 0.2, 0.9, date(2026, 5, 1), 90, 3))

    assert recover_pitcher_state(
        repo.get_many([p1.id])[p1.id], p1.id, game_date, 70
    ) == repo.get_with_recovery(p1.id, game_date, 70)


# ---------------------------------------------------------------------------
# delete / clear
# ---------------------------------------------------------------------------


def test_delete(repo, players):
    p1, _ = players
    repo.save_pitcher_state(PitcherState(p1.id, 0.5, 1.0))
    assert repo.delete(p1.id) is True
    assert repo.get(p1.id) is None


def test_clear_all(repo, players):
    p1, p2 = players
    repo.save_pitcher_state(PitcherState(p1.id, 0.5, 1.0))
    repo.save_pitcher_state(PitcherState(p2.id, 0.5, 1.0))

    deleted = repo.clear_all_pitcher_state()
    assert deleted >= 2
    assert repo.get(p1.id) is None
    assert repo.get(p2.id) is None


def test_facilities_speed_pitcher_recovery():
    """Better Facilities bring a tired pitcher back faster (rate_mult)."""
    stored = PitcherState("p", 0.2, 1.0, date(2026, 5, 1), 90, 0)
    game_date = date(2026, 5, 3)  # one full day of rest
    slow = recover_pitcher_state(stored, "p", game_date, 50, 0.85)
    normal = recover_pitcher_state(stored, "p", game_date, 50)
    fast = recover_pitcher_state(stored, "p", game_date, 50, 1.15)

    assert slow.current_energy < normal.current_energy < fast.current_energy
    assert recover_pitcher_state(stored, "p", game_date, 50, 1.0) == normal
