# tests/api/test_lobby_teams.py
"""Teams in the lobby (src/api/services/lobby_teams.py): every GM waiting in
the lobby is dealt a team by name, a person joining takes the team of the AI
GM they replace, and the start hands each GM the team they were dealt."""

import random

from src.api.services import lobby_teams
from src.api.services import personas as persona_service
from src.db.repositories.gm_repo import GMRepository


def _teams(db, league_id):
    rows = db.execute(
        "SELECT id, is_ai, lobby_city, lobby_mascot FROM gms WHERE league_id = %s",
        (league_id,),
    ).fetchall()
    return {r["id"]: (r["lobby_city"], r["lobby_mascot"]) for r in rows}


def _waiting(db, factory, league, is_ai=False):
    """A GM in the lobby: no team row yet."""
    gm = factory.gm(league=league, is_ai=is_ai)
    db.execute("UPDATE gms SET team_id = NULL WHERE id = %s", (gm.id,))
    return gm


def _lobby(db, factory, num_teams=4):
    league = factory.league(state="lobby")
    db.execute(
        "UPDATE leagues SET num_teams = %s WHERE id = %s", (num_teams, league.id)
    )
    me = _waiting(db, factory, league)
    persona_service.fill_lobby(db, league.id, random.Random(1))
    return league, me


def test_every_lobby_gm_is_dealt_a_different_pool_team(db_conn, factory):
    league, me = _lobby(db_conn, factory)

    teams = _teams(db_conn, league.id)

    assert len(teams) == 4
    assert me.id in teams
    assert all(t[0] for t in teams.values())
    assert len(set(teams.values())) == 4
    assert set(teams.values()) <= set(lobby_teams.pool_teams())


def test_a_person_joining_takes_the_replaced_ai_gms_team(db_conn, factory):
    league, _ = _lobby(db_conn, factory, num_teams=len(lobby_teams.pool_teams()))
    before = _teams(db_conn, league.id)

    friend = GMRepository(db_conn).create_gm(
        league_id=league.id, user_id=None, display_name="Friend"
    )
    persona_service.fill_lobby(db_conn, league.id)

    after = _teams(db_conn, league.id)
    (gone,) = set(before) - set(after)
    assert after[friend] == before[gone]
    assert all(after[g] == t for g, t in before.items() if g != gone)


def test_an_ai_gm_filling_in_for_a_leaver_gets_their_team(db_conn, factory):
    league, me = _lobby(db_conn, factory, num_teams=len(lobby_teams.pool_teams()))
    friend = GMRepository(db_conn).create_gm(
        league_id=league.id, user_id=None, display_name="Friend"
    )
    persona_service.fill_lobby(db_conn, league.id)
    friends_team = _teams(db_conn, league.id)[friend]

    GMRepository(db_conn).delete_gm(friend)
    persona_service.fill_lobby(db_conn, league.id)

    assert friends_team in _teams(db_conn, league.id).values()


def test_a_reroll_keeps_the_team(db_conn, factory):
    league, _ = _lobby(db_conn, factory)
    ai = persona_service.lobby_ai_gms(db_conn, league.id)[0]

    persona_service.reroll(db_conn, league.id, ai["id"])

    assert _teams(db_conn, league.id)[ai["id"]] == (
        ai["lobby_city"],
        ai["lobby_mascot"],
    )


def test_nothing_is_dealt_once_the_league_started(db_conn, factory):
    league = factory.league(state="season")
    gm = _waiting(db_conn, factory, league)

    lobby_teams.deal(db_conn, league.id)

    assert _teams(db_conn, league.id)[gm.id] == (None, None)


def test_claims_match_the_new_teams_by_name(db_conn, factory):
    league = factory.league(state="lobby")
    a = factory.team(city="Claimtown", mascot="Alphas")
    b = factory.team(city="Claimtown", mascot="Betas")
    gm = _waiting(db_conn, factory, league)
    other = _waiting(db_conn, factory, league, is_ai=True)
    db_conn.execute(
        "UPDATE gms SET lobby_city = 'Claimtown', lobby_mascot = 'Betas' WHERE id = %s",
        (gm.id,),
    )

    claims = lobby_teams.claims(db_conn, league.id, [a.id, b.id])

    assert claims == {gm.id: b.id}
    assert other.id not in claims


def _team_of(db, gm_id):
    r = db.execute(
        "SELECT lobby_city, lobby_mascot FROM gms WHERE id = %s", (gm_id,)
    ).fetchone()
    return (r["lobby_city"], r["lobby_mascot"])


def test_picking_an_ai_gms_team_swaps_with_it(db_conn, factory):
    league, me = _lobby(db_conn, factory)
    mine = _team_of(db_conn, me.id)
    ai = persona_service.lobby_ai_gms(db_conn, league.id)[0]
    theirs = (ai["lobby_city"], ai["lobby_mascot"])

    assert lobby_teams.pick(db_conn, league.id, me.id, *theirs)

    assert _team_of(db_conn, me.id) == theirs
    assert _team_of(db_conn, ai["id"]) == mine


def test_picking_an_open_team_frees_yours(db_conn, factory):
    league, me = _lobby(db_conn, factory)
    # An AI GM leaves, so one of the league's teams is open.
    db_conn.execute(
        """DELETE FROM gms WHERE id = (
               SELECT id FROM gms WHERE league_id = %s AND is_ai LIMIT 1)""",
        (league.id,),
    )
    held = set(_teams(db_conn, league.id).values())
    open_team = next(
        t for t in lobby_teams.league_teams(db_conn, league.id) if t not in held
    )
    mine = _team_of(db_conn, me.id)

    assert lobby_teams.pick(db_conn, league.id, me.id, *open_team)

    assert _team_of(db_conn, me.id) == open_team
    assert mine not in set(_teams(db_conn, league.id).values())
    assert len(set(_teams(db_conn, league.id).values())) == 3


def _set_league(db, league_id, me_id, mine, others):
    """The league plays with ``mine`` and ``others``; I hold mine, the lobby's
    AI GMs the others, in order."""
    db.execute("DELETE FROM league_lobby_teams WHERE league_id = %s", (league_id,))
    for city, mascot in [mine, *others]:
        db.execute(
            "INSERT INTO league_lobby_teams (league_id, city, mascot) VALUES (%s, %s, %s)",
            (league_id, city, mascot),
        )
    db.execute(
        "UPDATE gms SET lobby_city = %s, lobby_mascot = %s WHERE id = %s",
        (*mine, me_id),
    )
    ais = persona_service.lobby_ai_gms(db, league_id)
    for ai, (city, mascot) in zip(ais, others):
        db.execute(
            "UPDATE gms SET lobby_city = %s, lobby_mascot = %s WHERE id = %s",
            (city, mascot, ai["id"]),
        )
    return ais


def test_the_league_keeps_its_teams_once_drawn(db_conn, factory):
    league, _ = _lobby(db_conn, factory)
    first = lobby_teams.league_teams(db_conn, league.id)

    assert len(first) == 4
    assert set(_teams(db_conn, league.id).values()) == set(first)
    assert lobby_teams.league_teams(db_conn, league.id) == first


def test_picking_a_team_outside_the_league_brings_it_in(db_conn, factory):
    league, me = _lobby(db_conn, factory)
    ais = _set_league(
        db_conn,
        league.id,
        me.id,
        ("New York", "Titans"),
        [("London", "Lions"), ("Tokyo", "Samurai"), ("Sydney", "Sharks")],
    )

    assert lobby_teams.pick(db_conn, league.id, me.id, "Paris", "Musketeers")

    # London, the closest team no person holds, makes way; its AI GM gets
    # New York, the team I gave up.
    assert set(lobby_teams.league_teams(db_conn, league.id)) == {
        ("New York", "Titans"),
        ("Paris", "Musketeers"),
        ("Tokyo", "Samurai"),
        ("Sydney", "Sharks"),
    }
    assert _team_of(db_conn, me.id) == ("Paris", "Musketeers")
    assert _team_of(db_conn, ais[0]["id"]) == ("New York", "Titans")
    assert _team_of(db_conn, ais[1]["id"]) == ("Tokyo", "Samurai")


def test_bringing_in_a_team_near_your_own_trades_yours_out(db_conn, factory):
    league, me = _lobby(db_conn, factory)
    ais = _set_league(
        db_conn,
        league.id,
        me.id,
        ("London", "Lions"),
        [("New York", "Titans"), ("Tokyo", "Samurai"), ("Sydney", "Sharks")],
    )

    assert lobby_teams.pick(db_conn, league.id, me.id, "Paris", "Musketeers")

    assert ("London", "Lions") not in lobby_teams.league_teams(db_conn, league.id)
    assert _team_of(db_conn, me.id) == ("Paris", "Musketeers")
    assert [_team_of(db_conn, a["id"]) for a in ais] == [
        ("New York", "Titans"),
        ("Tokyo", "Samurai"),
        ("Sydney", "Sharks"),
    ]


def test_a_person_held_team_never_makes_way(db_conn, factory):
    league, me = _lobby(db_conn, factory, num_teams=2)
    friend = GMRepository(db_conn).create_gm(
        league_id=league.id, user_id=None, display_name="Friend"
    )
    persona_service.fill_lobby(db_conn, league.id)
    friends = _team_of(db_conn, friend)
    outside = next(
        t
        for t in lobby_teams.pool_teams()
        if t not in lobby_teams.league_teams(db_conn, league.id)
    )

    # With people holding every team, only my own can make way.
    assert lobby_teams.pick(db_conn, league.id, me.id, *outside)

    assert _team_of(db_conn, me.id) == outside
    assert _team_of(db_conn, friend) == friends
    assert set(lobby_teams.league_teams(db_conn, league.id)) == {outside, friends}


def test_the_choices_are_the_whole_pool(db_conn, factory):
    league, me = _lobby(db_conn, factory)

    choices = lobby_teams.choices(db_conn, league.id)

    assert {(c["city"], c["mascot"]) for c in choices} == set(lobby_teams.pool_teams())
    assert sum(c["in_league"] for c in choices) == 4
    mine = next(c for c in choices if c["holder_id"] == me.id)
    assert mine["in_league"] and not mine["is_ai"]


def test_another_persons_team_cant_be_picked(db_conn, factory):
    league, me = _lobby(db_conn, factory)
    friend = GMRepository(db_conn).create_gm(
        league_id=league.id, user_id=None, display_name="Friend"
    )
    persona_service.fill_lobby(db_conn, league.id)
    friends = _team_of(db_conn, friend)
    mine = _team_of(db_conn, me.id)

    assert not lobby_teams.pick(db_conn, league.id, me.id, *friends)
    assert _team_of(db_conn, me.id) == mine


def test_only_people_in_the_lobby_pick_real_teams(db_conn, factory):
    league, me = _lobby(db_conn, factory)
    ai = persona_service.lobby_ai_gms(db_conn, league.id)[0]
    team = lobby_teams.pool_teams()[0]

    assert not lobby_teams.pick(db_conn, league.id, me.id, "Nowhere", "Nobodies")
    assert not lobby_teams.pick(db_conn, league.id, ai["id"], *team)
    db_conn.execute("UPDATE leagues SET state = 'draft' WHERE id = %s", (league.id,))
    assert not lobby_teams.pick(db_conn, league.id, me.id, *team)
