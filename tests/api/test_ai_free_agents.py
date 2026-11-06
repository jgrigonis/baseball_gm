# tests/api/test_ai_free_agents.py
"""AI teams claiming off waivers and signing free agents to fill holes
(src/api/services/ai_free_agents.py, free agency phase 2)."""

import random
from types import SimpleNamespace

import pytest

from src.api.services import ai_free_agents, free_agents, waivers
from src.db.repositories.budget_repo import BudgetRepository
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.waiver_repo import WaiverRepository

GAME_DAYS = [f"2026-04-{d:02d}" for d in range(2, 12)]


@pytest.fixture
def lg(db_conn, factory):
    league = factory.league(state="season", mode="blitz")
    db_conn.execute(
        "UPDATE leagues SET sim_period_days = 1 WHERE id = %s", (league.id,)
    )
    season = factory.season(year=2026)
    factory.league_season(league, season)
    mine = factory.team(city="My", mascot="Team")
    ai = factory.team(city="Ai", mascot="Club")
    for t in (mine, ai):
        factory.league_season_team(league, season, t)
    factory.gm(team=mine, league=league, is_ai=False)
    factory.gm(team=ai, league=league, is_ai=True)
    for day in GAME_DAYS:
        db_conn.execute(
            """INSERT INTO games (id, game_date, season_id, home_team_id,
                                  away_team_id, completed)
               VALUES (%s, %s, %s, %s, %s, 0)""",
            (factory._id(), day, season.id, mine.id, ai.id),
        )
    BudgetRepository(db_conn).for_league(league.id, 2026)
    return SimpleNamespace(
        db=db_conn,
        factory=factory,
        league=league,
        season=season,
        mine=mine,
        ai=ai,
        contracts=ContractRepository(db_conn),
        status=PlayerStatusRepository(db_conn),
    )


@pytest.fixture(autouse=True)
def roomy_owners(monkeypatch):
    monkeypatch.setattr(BudgetRepository, "refusal", lambda *a, **k: None)
    monkeypatch.setattr(ai_free_agents, "_budget_room", lambda *a: float("inf"))


def _free_agent(lg, level, **kw):
    pid = lg.factory.rated_player(
        lg.mine, lg.league, level, status="free_agent", **kw
    ).id
    lg.db.execute("DELETE FROM team_players WHERE player_id = %s", (pid,))
    return pid


def _team_ids(lg, team):
    return PlayerRepository(lg.db).get_player_ids_from_team_players(team.id)


# ── Holes ─────────────────────────────────────────────────────────────────────


def test_role_values_read_the_5th_starter_and_8th_reliever():
    rated = {
        f"p{i}": {"sp": 80 - i, "rp": 70 - i, "overall_offense": 0} for i in range(13)
    }
    have = ai_free_agents.role_values(rated)
    assert have["sp"] == 76  # p0..p4 start
    assert have["rp"] == 70 - 12  # p5..p12 relieve, the 8th is p12


def test_best_fit_needs_a_clear_gain():
    team = {"sp": 50, "rp": 50, "c": 50}
    assert ai_free_agents.best_fit(team, {"sp": 53}) == (None, 0.0)
    assert ai_free_agents.best_fit(team, {"sp": 58, "rp": 60}) == ("rp", 10)


# ── Free agents ───────────────────────────────────────────────────────────────


def test_an_ai_team_signs_a_free_agent_who_fills_a_hole(lg):
    for _ in range(3):
        lg.factory.rated_player(lg.ai, lg.league, level=40)
    pid = _free_agent(lg, 75, pitcher=True)
    signed = ai_free_agents.sign_free_agents(
        lg.db, lg.league.id, lg.season.id, [lg.ai.id], 2026, GAME_DAYS[0]
    )
    assert signed == [(lg.ai.id, pid)]
    assert pid in _team_ids(lg, lg.ai)
    assert lg.contracts.active(pid, 2026)["team_id"] == lg.ai.id


def test_no_hole_no_signing(lg):
    for _ in range(14):
        lg.factory.rated_player(lg.ai, lg.league, level=80)
    _free_agent(lg, 50)
    assert (
        ai_free_agents.sign_free_agents(
            lg.db, lg.league.id, lg.season.id, [lg.ai.id], 2026, GAME_DAYS[0]
        )
        == []
    )


def test_an_ai_team_stays_inside_its_budget(lg, monkeypatch):
    lg.factory.rated_player(lg.ai, lg.league, level=40)
    _free_agent(lg, 75)
    monkeypatch.setattr(ai_free_agents, "_budget_room", lambda *a: 0)
    assert (
        ai_free_agents.sign_free_agents(
            lg.db, lg.league.id, lg.season.id, [lg.ai.id], 2026, GAME_DAYS[0]
        )
        == []
    )


def test_a_full_minors_lets_a_never_guaranteed_prospect_go(lg, monkeypatch):
    monkeypatch.setattr(ai_free_agents, "MINORS_LIMIT", 2)
    monkeypatch.setattr(free_agents, "MINORS_LIMIT", 2)
    weak = lg.factory.rated_player(lg.ai, lg.league, level=20, status="minors").id
    lg.factory.rated_player(lg.ai, lg.league, level=30, status="minors")
    pid = _free_agent(lg, 75)
    signed = ai_free_agents.sign_free_agents(
        lg.db, lg.league.id, lg.season.id, [lg.ai.id], 2026, GAME_DAYS[0]
    )
    assert signed == [(lg.ai.id, pid)]
    assert lg.status.get_status(weak) == "free_agent"
    assert weak not in _team_ids(lg, lg.ai)


def test_people_teams_are_never_shopped_for(lg):
    teams = ai_free_agents._ai_teams(
        lg.db, lg.league.id, lg.season.id, random.Random(1)
    )
    assert teams == [lg.ai.id]


# ── Waivers ───────────────────────────────────────────────────────────────────


def test_an_ai_team_claims_a_waiver_player_who_fills_a_hole(lg):
    lg.factory.rated_player(lg.ai, lg.league, level=40)
    pid = lg.factory.rated_player(lg.mine, lg.league, level=75).id
    lg.contracts.sign_unsigned(lg.league.id, 2026)
    free_agents.release(lg.db, lg.league.id, lg.mine.id, pid)

    assert ai_free_agents.claim_waivers(lg.db, lg.league.id, [lg.ai.id], 2026) == 1
    assert pid in WaiverRepository(lg.db).claims_by(lg.league.id, lg.ai.id)
    # Claimed once is enough.
    assert ai_free_agents.claim_waivers(lg.db, lg.league.id, [lg.ai.id], 2026) == 0
    waivers.clear_all(lg.db, lg.league.id)
    assert pid in _team_ids(lg, lg.ai)
