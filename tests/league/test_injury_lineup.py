# tests/league/test_injury_lineup.py
"""Strategy tab Injury Lineup: when the sim rebuilds a person's saved batting
orders for an injury (src/league/injury_lineup.py)."""

from types import SimpleNamespace

import pytest

from src.db.repositories.lineup_preference_repo import LineupPreferenceRepository
from src.db.repositories.team_repo import TeamRepository
from src.league import injury_lineup
from src.team.manager_profile import ManagerProfile
from src.team.team_in_game import TeamInGame


def test_days_out_counts_rested_rust_at_double_speed():
    assert injury_lineup.days_out(1, 5, rest_rusty=False) == 1
    assert injury_lineup.days_out(1, 5, rest_rusty=True) == 4  # 1 + ceil(5/2)


def _fake_team(mode, rest_rusty=False):
    players = [SimpleNamespace(id=f"h{i}", pitcher_fatigue=None) for i in range(12)]
    players.append(SimpleNamespace(id="p0", pitcher_fatigue=object()))
    profile = ManagerProfile(injury_lineup=mode, rest_rusty=rest_rusty)
    return SimpleNamespace(players=players, profile=profile)


LENGTHS = {
    "h0": {"length": 1, "rust_days": 4},  # 1 day, or 3 resting the rust
    "h1": {"length": 10, "rust_days": 0},
    "p0": {"length": 20, "rust_days": 0},
}


def key(mode, hurt, rust=(), rest_rusty=False, out=()):
    team = _fake_team(mode, rest_rusty)
    return injury_lineup.absence_key(
        team, None, set(hurt), set(hurt) | set(out), dict.fromkeys(rust), LENGTHS
    )


def test_always_rebuild_counts_every_hurt_hitter():
    assert key("rebuild", {"h0", "h1"}) == "h0:out,h1:out"


def test_pitchers_never_count():
    assert key("rebuild", {"p0"}) == ""


def test_short_outs_are_auto_filled():
    assert key("fill-1", {"h0", "h1"}) == "h1:out"
    assert key("fill-2", {"h0", "h1"}) == "h1:out"
    assert key("fill-10", {"h0", "h1"}) == ""


def test_resting_rust_makes_a_short_out_long():
    assert key("fill-2", {"h0"}, rest_rusty=True) == "h0:out"


def test_back_but_rusty_is_its_own_step():
    # Back from the injury, playing through rust
    assert key("rebuild", set(), rust={"h1"}) == "h1:rusty"
    # Rest rusty sits him: still out
    assert key("rebuild", set(), rust={"h1"}, out={"h1"}) == "h1:out"
    # Rust gone
    assert key("rebuild", set()) == ""


@pytest.fixture
def team_setup(db_conn, factory):
    league = factory.league(state="season", mode="blitz")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=False)
    hitters = [
        factory.rated_player(team, league, 40 + 5 * i, status="26man", name=f"H{i}")
        for i in range(11)
    ]
    db_conn.execute(
        "UPDATE gm_profiles SET injury_lineup = 'rebuild' WHERE gm_id = %s", (gm.id,)
    )
    return league, team, gm, hitters


def _game_team(db_conn, team, mode="rebuild"):
    t = TeamInGame(TeamRepository(db_conn).get(team.id))
    t.profile = ManagerProfile(injury_lineup=mode)
    return t


def _hurt(db_conn, league, player, days):
    db_conn.execute(
        """INSERT INTO player_injuries (player_id, league_id, games_remaining, return_date)
           VALUES (%s, %s, %s, '2099-01-01')""",
        (player.id, league.id, days),
    )


def _saved(db_conn, gm, hand):
    return {
        s["player_id"]
        for s in LineupPreferenceRepository(db_conn).get_by_gm_id(gm.id)[hand]
    }


def test_first_look_only_notes_who_is_out(db_conn, team_setup):
    league, team, gm, hitters = team_setup
    _hurt(db_conn, league, hitters[-1], 10)
    t = _game_team(db_conn, team)
    hurt = {hitters[-1].id}
    assert not injury_lineup.rebuild_if_needed(
        db_conn, league.id, t, None, hurt, hurt, {}
    )
    assert _saved(db_conn, gm, "R") == set()


def test_a_long_injury_rebuilds_and_saves_both_hands(db_conn, team_setup):
    league, team, gm, hitters = team_setup
    t = _game_team(db_conn, team)
    # Everyone healthy: noted
    injury_lineup.rebuild_if_needed(db_conn, league.id, t, None, set(), set(), {})
    best = hitters[-1]
    _hurt(db_conn, league, best, 10)
    hurt = {best.id}
    assert injury_lineup.rebuild_if_needed(db_conn, league.id, t, None, hurt, hurt, {})
    for hand in ("R", "L"):
        saved = _saved(db_conn, gm, hand)
        assert len(saved) == 9 and best.id not in saved
    # Same news next game: no rebuild
    assert not injury_lineup.rebuild_if_needed(
        db_conn, league.id, t, None, hurt, hurt, {}
    )
    # He's back: rebuilt with him in
    assert injury_lineup.rebuild_if_needed(
        db_conn, league.id, t, None, set(), set(), {}
    )
    assert best.id in _saved(db_conn, gm, "R")


def test_a_short_injury_is_auto_filled(db_conn, team_setup):
    league, team, gm, hitters = team_setup
    t = _game_team(db_conn, team, mode="fill-2")
    injury_lineup.rebuild_if_needed(db_conn, league.id, t, None, set(), set(), {})
    _hurt(db_conn, league, hitters[-1], 2)
    hurt = {hitters[-1].id}
    assert not injury_lineup.rebuild_if_needed(
        db_conn, league.id, t, None, hurt, hurt, {}
    )
    assert _saved(db_conn, gm, "R") == set()


def test_always_auto_fill_never_rebuilds(db_conn, team_setup):
    league, team, gm, hitters = team_setup
    t = _game_team(db_conn, team, mode="fill")
    _hurt(db_conn, league, hitters[-1], 30)
    hurt = {hitters[-1].id}
    for _ in range(2):
        assert not injury_lineup.rebuild_if_needed(
            db_conn, league.id, t, None, hurt, hurt, {}
        )


# ── Lineup Updates: Rebuild daily ─────────────────────────────────────────────


def _daily_team(db_conn, team):
    t = TeamInGame(TeamRepository(db_conn).get(team.id))
    t.profile = ManagerProfile(lineup_updates="daily")
    return t


def test_rebuild_daily_saves_both_hands_then_keeps_them(db_conn, team_setup):
    league, team, gm, hitters = team_setup
    t = _daily_team(db_conn, team)
    assert injury_lineup.update_lineups(db_conn, league.id, t, None, set(), set(), {})
    first = {h: _saved(db_conn, gm, h) for h in ("R", "L")}
    assert all(len(v) == 9 for v in first.values())
    # Nothing new: the saved lineups stand
    assert not injury_lineup.update_lineups(
        db_conn, league.id, t, None, set(), set(), {}
    )
    assert {h: _saved(db_conn, gm, h) for h in ("R", "L")} == first


def test_rebuild_daily_takes_out_the_injured(db_conn, team_setup):
    league, team, gm, hitters = team_setup
    t = _daily_team(db_conn, team)
    injury_lineup.update_lineups(db_conn, league.id, t, None, set(), set(), {})
    best = hitters[-1]
    assert best.id in _saved(db_conn, gm, "R")
    hurt = {best.id}
    assert injury_lineup.update_lineups(db_conn, league.id, t, None, hurt, hurt, {})
    assert best.id not in _saved(db_conn, gm, "R")


def test_keep_mine_never_rebuilds_without_injury_lineup(db_conn, team_setup):
    league, team, gm, hitters = team_setup
    t = _game_team(db_conn, team, mode="fill")
    assert not injury_lineup.update_lineups(
        db_conn, league.id, t, None, set(), set(), {}
    )
    assert _saved(db_conn, gm, "R") == set()
