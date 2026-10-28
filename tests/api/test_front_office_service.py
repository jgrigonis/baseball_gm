# tests/api/test_front_office_service.py
"""AI front offices (src/api/services/front_office.py): each AI team's
outlook from its state and persona, and what it changes in the draft, the
roster, call-ups and the sim's lineups."""

import random
from types import SimpleNamespace

import pytest

from src.api.services import front_office, team_states
from src.api.services import personas as persona_service
from src.api.services.draft_needs import draft_strategies
from src.db.repositories.persona_repo import PersonaRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.team_repo import TeamRepository
from src.db.repositories.team_state_repo import TeamStateRepository
from src.league import front_office as rules
from src.league import personas
from src.league.play_season import _set_front_office
from src.team.team_in_game import TeamInGame

TODAY = "2025-04-04"


def _persona(db, **dials):
    repo = PersonaRepository(db)
    pid = repo.create(
        f"Front Office {random.random()}",
        "A test.",
        "The Tester",
        personas.clean(dials),
        50,
    )
    return repo.get(pid)


def _state(lg, team, state, day=TODAY):
    TeamStateRepository(lg.db).add(
        lg.league.id, lg.season.id, team.id, day, state, 0, state, {"tier": 0}
    )


@pytest.fixture
def lg(db_conn, factory):
    """A person's team and an AI team, 13 hitters and 13 pitchers each at 58,
    both retooling."""
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
    ns = SimpleNamespace(
        db=db_conn,
        league=league,
        season=season,
        mine=mine,
        theirs=theirs,
        ai=ai,
        factory=factory,
    )
    for t in (mine, theirs):
        _state(ns, t, "retooling")
    return ns


def test_only_ai_teams_have_an_outlook(lg):
    persona_service.assign(lg.db, lg.ai.id, _persona(lg.db, youth=100))
    out = front_office.outlooks(lg.db, lg.league.id, lg.season.id, TODAY)
    assert set(out) == {lg.theirs.id}
    o = out[lg.theirs.id]
    assert o.state == "retooling"
    assert o.lean.youth == 100
    assert o.tilt == pytest.approx(rules.PERSONA_YOUTH)


def test_a_rebuilding_team_calls_up_its_kid(lg):
    kid = lg.factory.rated_player(lg.theirs, lg.league, 57, age=21, status="minors")
    vet = lg.factory.rated_player(lg.theirs, lg.league, 58, age=34)
    status = PlayerStatusRepository(lg.db)

    o = front_office.outlooks(lg.db, lg.league.id, lg.season.id, TODAY)[lg.theirs.id]
    front_office.replan_roster(
        lg.db, lg.league.id, lg.season.id, lg.theirs.id, o, TODAY
    )
    assert status.get_status(kid.id) != "26man"

    _state(lg, lg.theirs, "rebuilding", "2025-04-05")
    changed = {lg.theirs.id: "rebuilding", lg.mine.id: "rebuilding"}
    assert front_office.call_ups(lg.db, lg.league.id, changed, "2025-04-05") == 1
    assert status.get_status(kid.id) == "26man"
    assert status.get_status(vet.id) != "26man"


def test_a_checkpoint_reports_whose_state_changed(lg, monkeypatch):
    monkeypatch.setattr(team_states, "CHECKPOINT_DAYS", 0)
    before = {
        t: r["state"]
        for t, r in TeamStateRepository(lg.db)
        .latest(lg.league.id, lg.season.id)
        .items()
    }
    changed = team_states.refresh_if_due(lg.db, lg.league.id, "2025-04-12")
    after = TeamStateRepository(lg.db).latest(lg.league.id, lg.season.id)
    assert all(before[t] != s == after[t]["state"] for t, s in changed.items())
    assert {t for t in before if before[t] != after[t]["state"]} == set(changed)


def test_an_ai_teams_draft_strategy_reads_its_outlook(lg):
    draft = lg.factory.draft(league=lg.league, season=lg.season)
    lg.factory.draft_order(draft, [lg.mine, lg.theirs])
    persona_service.assign(
        lg.db, lg.ai.id, _persona(lg.db, youth=100, risk=100, offense_defense=95)
    )
    _state(lg, lg.theirs, "rebuilding", "2025-04-05")

    strategies = draft_strategies(lg.db, draft.id, lg.league.id, cached=False)

    ai = strategies[lg.theirs.id]
    assert ai.chips.get("offense", 0) >= 2
    assert ai.age_pref == -1.0
    assert strategies[lg.mine.id].age_pref == 0


def _in_game(lg, team):
    return TeamInGame(TeamRepository(lg.db).get(team.id))


def test_the_sim_plays_kids_and_protects_arms_on_a_rebuilding_ai_team(lg):
    kid = lg.factory.rated_player(lg.theirs, lg.league, 57, age=21)
    persona_service.assign(
        lg.db, lg.ai.id, _persona(lg.db, youth=100, offense_defense=0)
    )
    _state(lg, lg.theirs, "rebuilding", "2025-04-05")
    ai, mine = _in_game(lg, lg.theirs), _in_game(lg, lg.mine)

    _set_front_office(lg.db, lg.league.id, lg.season.id, ai, mine)

    assert ai.form[kid.id] == pytest.approx(rules.MAX_AGE_POINTS)
    assert ai.defense_weight == pytest.approx(1.5)
    assert ai.profile.tired_starters == "protect"
    # A person's team is left alone.
    assert mine.form == {}
    assert mine.defense_weight == 1.0
    assert mine.profile.tired_starters == "standard"
