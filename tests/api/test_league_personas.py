# tests/api/test_league_personas.py
"""GM personas in a league (src/api/services/personas.py): the seeded
library, picking and assigning one, and what a persona changes in trades and
team state."""

import random
from types import SimpleNamespace

import pytest

from src.api.services import personas as persona_service
from src.api.services import team_states, trades
from src.db.repositories.gm_repo import GMRepository
from src.db.repositories.persona_repo import PersonaRepository
from src.db.repositories.player_season_stats_repo import PlayerSeasonStatsRepository
from src.league import personas


def _persona(db, name=None, chance=50, **dials):
    repo = PersonaRepository(db)
    name = name or f"Test Persona {random.random()}"
    pid = repo.create(name, "A test.", "The Tester", personas.clean(dials), chance)
    return repo.get(pid)


def test_the_library_is_seeded(db_conn):
    rows = PersonaRepository(db_conn).all()
    assert len(rows) >= 100
    assert all(set(r["dials"]) == set(personas.DIALS) for r in rows)


def test_assign_names_the_gm_and_sets_its_tactics(db_conn, factory):
    league = factory.league(state="season")
    gm = factory.gm(team=factory.team(), league=league)
    p = _persona(db_conn, small_ball=95, bullpen_hook=10)

    persona_service.assign(db_conn, gm.id, p)

    row = GMRepository(db_conn).get_by_id(gm.id)
    assert row["persona_id"] == p["id"]
    assert row["display_name"] == p["name"]
    profile = GMRepository(db_conn).get_profile(gm.id)
    assert profile["sac_bunt"] == "frequent"
    assert profile["starter_usage"] == "long"
    assert profile["stats_vs_scouting"] == 50


def test_a_pick_skips_personas_already_in_the_league(db_conn, factory):
    db_conn.execute("UPDATE gm_personas SET chance = 0")
    a = _persona(db_conn, chance=50)
    b = _persona(db_conn, chance=50)
    league = factory.league(state="season")
    gm = factory.gm(team=factory.team(), league=league)
    persona_service.assign(db_conn, gm.id, a)

    rng = random.Random(4)
    picks = {persona_service.pick(db_conn, league.id, rng)["id"] for _ in range(20)}
    assert picks == {b["id"]}


def test_with_nothing_pickable_the_gm_is_a_plain_ai_manager(db_conn, factory):
    db_conn.execute("UPDATE gm_personas SET chance = 0")
    league = factory.league(state="season")
    gm = factory.gm(team=factory.team(), league=league)

    persona_service.give_persona(db_conn, league.id, gm.id, random.Random())

    row = GMRepository(db_conn).get_by_id(gm.id)
    assert row["persona_id"] is None
    assert row["display_name"] == "AI Manager"


def test_leanings_come_from_the_persona_or_the_persons_setting(db_conn, factory):
    league = factory.league(state="season")
    ai_team, my_team = factory.team(), factory.team()
    ai = factory.gm(team=ai_team, league=league)
    me = factory.gm(team=my_team, league=league, is_ai=False)
    persona_service.assign(
        db_conn,
        ai.id,
        _persona(db_conn, risk=90, time_horizon=10, stats_vs_scouting=80),
    )
    GMRepository(db_conn).save_profile(me.id, {"stats_vs_scouting": 25})

    lean = persona_service.leanings(db_conn, league.id)
    assert lean[ai_team.id].risk == 90
    assert lean[ai_team.id].time_horizon == 10
    assert lean[ai_team.id].stats_vs_scouting == 80
    assert lean[my_team.id] == personas.Leanings(stats_vs_scouting=25)


def test_a_persona_in_a_league_cant_be_deleted(db_conn, factory):
    repo = PersonaRepository(db_conn)
    used, spare = _persona(db_conn), _persona(db_conn)
    gm = factory.gm(team=factory.team(), league=factory.league(state="season"))
    persona_service.assign(db_conn, gm.id, used)

    assert repo.leagues_using(used["id"]) == 1
    assert not repo.delete(used["id"])
    assert repo.get(used["id"])
    assert repo.delete(spare["id"])
    assert repo.get(spare["id"]) is None


def test_chance_is_all_that_changes(db_conn):
    repo = PersonaRepository(db_conn)
    p = _persona(db_conn, chance=50)
    repo.set_chance(p["id"], 0)
    after = repo.get(p["id"])
    assert after["chance"] == 0
    assert after["dials"] == p["dials"]
    assert after["name"] == p["name"]


# ── What a persona changes ───────────────────────────────────────────────────


@pytest.fixture
def lg(db_conn, factory):
    """Two teams, 13 hitters and 13 pitchers each at 58: an AI team and a
    person's."""
    league = factory.league(state="season", mode="blitz")
    season = factory.season(year=2025)
    factory.league_season(league, season)
    mine = factory.team(city="My", mascot="Team")
    theirs = factory.team(city="AI", mascot="Club")
    for t in (mine, theirs):
        factory.league_season_team(league, season, t)
    factory.gm(team=mine, league=league, is_ai=False)
    ai = factory.gm(team=theirs, league=league, is_ai=True)
    for t in (mine, theirs):
        for _ in range(13):
            factory.rated_player(t, league, 58)
            factory.rated_player(t, league, 58, pitcher=True)
    return SimpleNamespace(
        db=db_conn,
        league=league,
        season=season,
        mine=mine,
        theirs=theirs,
        ai=ai,
        factory=factory,
    )


def _answer(lg, give, get):
    return trades.ai_answer(
        lg.db,
        lg.league.id,
        lg.season.id,
        lg.theirs.id,
        lg.mine.id,
        [p.id for p in get],
        [p.id for p in give],
        "2025-04-04",
    )


def test_a_gambler_wants_a_smaller_margin(lg):
    give = [lg.factory.rated_player(lg.mine, lg.league, 64)]
    get = [lg.factory.rated_player(lg.theirs, lg.league, 63)]
    neutral = _answer(lg, give, get)

    persona_service.assign(lg.db, lg.ai.id, _persona(lg.db, risk=100))
    gambler = _answer(lg, give, get)
    persona_service.assign(lg.db, lg.ai.id, _persona(lg.db, risk=0))
    cautious = _answer(lg, give, get)

    assert gambler.threshold == pytest.approx(neutral.threshold * 0.5)
    assert cautious.threshold == pytest.approx(neutral.threshold * 1.5)


def _season_stats(lg, player, **cols):
    names = ", ".join(cols)
    marks = ", ".join(["%s"] * len(cols))
    lg.db.execute(
        f"""INSERT INTO player_season_stats
            (player_id, season_id, team_id, {names})
            VALUES (%s, %s, %s, {marks})""",
        (player.id, lg.season.id, lg.mine.id, *cols.values()),
    )


def test_a_gm_who_trusts_stats_values_a_hot_hitter_more(lg):
    hot = lg.factory.rated_player(lg.mine, lg.league, 60)
    _season_stats(lg, hot, bat_ab=500, bat_hits=200, bat_home_runs=40, bat_walks=80)
    totals = PlayerSeasonStatsRepository(lg.db).get_form_totals(lg.season.id, [hot.id])
    assert totals[hot.id]["bat_ab"] == 500
    giving = [lg.factory.rated_player(lg.theirs, lg.league, 60)]

    persona_service.assign(lg.db, lg.ai.id, _persona(lg.db, stats_vs_scouting=0))
    scout = _answer(lg, [hot], giving)
    persona_service.assign(lg.db, lg.ai.id, _persona(lg.db, stats_vs_scouting=100))
    stats = _answer(lg, [hot], giving)

    assert stats.score > scout.score


def test_team_state_inputs_carry_the_gms_lean(lg):
    persona_service.assign(lg.db, lg.ai.id, _persona(lg.db, time_horizon=100, risk=100))
    inputs = team_states.gather(lg.db, lg.league.id, lg.season.id)
    assert inputs[lg.theirs.id].lean == 1.0
    assert inputs[lg.mine.id].lean == 0.0


# ── The lobby ─────────────────────────────────────────────────────────────────


def _lobby(db, factory, num_teams=4):
    league = factory.league(state="lobby")
    db.execute(
        "UPDATE leagues SET num_teams = %s WHERE id = %s", (num_teams, league.id)
    )
    GMRepository(db).create_gm(league_id=league.id, display_name="Al")
    return league


def test_the_lobby_picks_an_ai_gm_for_each_open_team(db_conn, factory):
    league = _lobby(db_conn, factory)

    persona_service.fill_lobby(db_conn, league.id)

    ai = persona_service.lobby_ai_gms(db_conn, league.id)
    assert len(ai) == 3
    assert all(g["persona_id"] and g["archetype"] for g in ai)
    assert len({g["persona_id"] for g in ai}) == 3


def test_filling_twice_changes_nothing(db_conn, factory):
    league = _lobby(db_conn, factory)
    persona_service.fill_lobby(db_conn, league.id)
    before = persona_service.lobby_ai_gms(db_conn, league.id)

    persona_service.fill_lobby(db_conn, league.id)

    assert persona_service.lobby_ai_gms(db_conn, league.id) == before


def test_a_person_joining_takes_the_newest_ai_gms_place(db_conn, factory):
    league = _lobby(db_conn, factory)
    persona_service.fill_lobby(db_conn, league.id)
    before = persona_service.lobby_ai_gms(db_conn, league.id)

    GMRepository(db_conn).create_gm(league_id=league.id, display_name="Bob")
    persona_service.fill_lobby(db_conn, league.id)

    assert persona_service.lobby_ai_gms(db_conn, league.id) == before[:2]


def test_reroll_picks_a_persona_not_yet_in_the_league(db_conn, factory):
    league = _lobby(db_conn, factory)
    persona_service.fill_lobby(db_conn, league.id)
    ai = persona_service.lobby_ai_gms(db_conn, league.id)

    assert persona_service.reroll(db_conn, league.id, ai[0]["id"], random.Random(1))

    after = persona_service.lobby_ai_gms(db_conn, league.id)
    assert after[0]["persona_id"] not in {g["persona_id"] for g in ai}
    assert after[1:] == ai[1:]
    row = GMRepository(db_conn).get_by_id(ai[0]["id"])
    assert row["display_name"] == after[0]["display_name"]


def test_reroll_leaves_people_alone(db_conn, factory):
    league = _lobby(db_conn, factory)
    al = GMRepository(db_conn).get_all_in_league(league.id)[0]

    assert not persona_service.reroll(db_conn, league.id, al["id"])
