# tests/api/test_lineup_autofill.py
"""The Lineup tab's Auto-fill and Rebuild (src/api/services/lineup_autofill.py)."""

import pytest

from src.api.services.lineup_autofill import autofill, eligible_hitters
from src.db.repositories.gm_repo import GMRepository

POSITIONS = {"c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "dh"}


@pytest.fixture
def team_setup(db_conn, factory):
    league = factory.league(state="season", mode="blitz")
    team = factory.team()
    factory.gm(team=team, league=league, is_ai=False)
    hitters = [
        factory.rated_player(team, league, 50 + i, status="26man", name=f"H{i}")
        for i in range(10)
    ]
    forty = factory.rated_player(team, league, 60, status="40man", name="Forty")
    minors = factory.rated_player(team, league, 99, status="minors", name="Minors")
    pitcher = factory.rated_player(team, league, 99, status="26man", pitcher=True)
    return league, team, hitters, forty, minors, pitcher


def ids(lineup):
    return [s["player_id"] for s in lineup]


def test_rebuild_makes_a_full_lineup_of_eligible_hitters(db_conn, team_setup):
    league, team, hitters, forty, minors, pitcher = team_setup

    lineup = autofill(db_conn, league.id, team.id, [None] * 9, rebuild=True)

    assert len(lineup) == 9 and len(set(ids(lineup))) == 9
    assert {s["position"] for s in lineup} == POSITIONS
    assert minors.id not in ids(lineup)
    assert pitcher.id not in ids(lineup)


def test_autofill_keeps_players_already_in_the_lineup(db_conn, team_setup):
    league, team, hitters, *_ = team_setup
    worst = hitters[0]  # rated 50, wouldn't make a rebuilt lineup
    current = [None] * 9
    current[4] = {"player_id": worst.id, "position": "ss"}

    lineup = autofill(db_conn, league.id, team.id, current, rebuild=False)

    assert lineup[4] == {"player_id": worst.id, "position": "ss"}
    assert len(set(ids(lineup))) == 9

    rebuilt = autofill(db_conn, league.id, team.id, current, rebuild=True)
    assert worst.id not in ids(rebuilt)


def test_injured_players_are_replaced(db_conn, team_setup):
    league, team, hitters, *_ = team_setup
    hurt = hitters[-1]
    db_conn.execute(
        "INSERT INTO player_injuries (player_id, league_id, return_date)"
        " VALUES (%s, %s, '2999-01-01')",
        (hurt.id, league.id),
    )
    current = [{"player_id": hurt.id, "position": "c"}] + [None] * 8

    lineup = autofill(db_conn, league.id, team.id, current, rebuild=False)

    assert hurt.id not in ids(lineup)
    assert {s["position"] for s in lineup} == POSITIONS


def test_long_form_plays_only_the_26_man(db_conn, factory, team_setup):
    league, team, hitters, forty, *_ = team_setup
    assert forty.id in {p.id for p in eligible_hitters(db_conn, league.id, team.id)}

    db_conn.execute("UPDATE leagues SET mode = 'longform' WHERE id = %s", (league.id,))

    assert forty.id not in {p.id for p in eligible_hitters(db_conn, league.id, team.id)}


def test_not_enough_hitters_raises(db_conn, factory):
    league = factory.league(state="season")
    team = factory.team()
    factory.gm(team=team, league=league, is_ai=False)
    for i in range(5):
        factory.rated_player(team, league, 50, status="26man")

    with pytest.raises(ValueError):
        autofill(db_conn, league.id, team.id, [], rebuild=True)


def test_profile_comes_from_the_strategy_tab(db_conn, factory):
    league = factory.league(state="season")
    team = factory.team()
    gm = factory.gm(team=team, league=league, is_ai=True)
    repo = GMRepository(db_conn)

    assert repo.get_team_profile(team.id, league.id)["lineup_style"] == "traditional"

    db_conn.execute(
        "UPDATE gm_profiles SET lineup_style = 'power-first' WHERE gm_id = %s",
        (gm.id,),
    )
    assert repo.get_team_profile(team.id, league.id)["lineup_style"] == "power-first"
    assert repo.get_team_profile(factory.team().id, league.id) is None


def test_platoon_setting_uses_the_hand_of_the_starter(db_conn, factory, team_setup):
    """A lefty bat just behind the regulars (the worst of whom is rated 52)
    plays against a righty starter under the aggressive platoon setting, and
    not against a lefty or with platoons off."""
    league, team, hitters, *_ = team_setup
    lefty = factory.rated_player(team, league, 51, status="26man", name="Lefty")
    db_conn.execute("UPDATE players SET bats = 'L' WHERE id = %s", (lefty.id,))
    gm_id = db_conn.execute(
        "SELECT id FROM gms WHERE team_id = %s", (team.id,)
    ).fetchone()["id"]
    off = autofill(db_conn, league.id, team.id, [None] * 9, True, vs_hand="R")
    assert lefty.id not in ids(off)

    GMRepository(db_conn).save_profile(gm_id, {"platoon_usage": "aggressive"})

    vs_r = autofill(db_conn, league.id, team.id, [None] * 9, True, vs_hand="R")
    vs_l = autofill(db_conn, league.id, team.id, [None] * 9, True, vs_hand="L")

    assert lefty.id in ids(vs_r)
    assert lefty.id not in ids(vs_l)
