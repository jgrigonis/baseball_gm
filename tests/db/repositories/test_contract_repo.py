# tests/db/repositories/test_contract_repo.py
"""Signing, renewing and reading contracts (src/db/repositories/contract_repo.py)."""

import pytest

from src.db.repositories import contract_repo
from src.db.repositories.contract_repo import ContractRepository
from src.player import contracts as ct


@pytest.fixture
def env(db_conn, factory):
    league = factory.league()
    season = factory.season(year=2026)
    factory.league_season(league, season)
    team = factory.team()
    factory.league_season_team(league, season, team)
    return db_conn, factory, league, season, team


def _draft(env, player_id, pick, year):
    db, factory, league, _, team = env
    season = factory.season(year=year)
    draft = factory.draft(league=league, season=season)
    gm = factory.gm(team=team, league=league)
    db.execute(
        "INSERT INTO draft_picks (draft_id, pick_number, round, gm_id, team_id, player_id)"
        " VALUES (%s, %s, 1, %s, %s, %s)",
        (draft.id, pick, gm.id, team.id, player_id),
    )


def test_starting_roster_gets_standard_deals_partway_through(env):
    db, factory, league, _, team = env
    ids = [factory.rated_player(team, league, level=60).id for _ in range(12)]
    repo = ContractRepository(db)
    assert repo.sign_unsigned(league.id, 2026) == 12
    deals = repo.active_for(ids, 2026)
    assert set(deals) == set(ids)
    assert all(d["kind"] == "standard" for d in deals.values())
    assert any(d["start_year"] < 2026 for d in deals.values())  # staggered
    # Signing again does nothing: everyone has a deal.
    assert repo.sign_unsigned(league.id, 2026) == 0


def test_drafted_player_gets_a_rookie_deal_from_his_draft_year(env):
    db, factory, league, _, team = env
    pid = factory.rated_player(team, league, status="minors", age=19).id
    _draft(env, pid, pick=1, year=2025)
    repo = ContractRepository(db)
    repo.sign_unsigned(league.id, 2026)
    deal = repo.active(pid, 2026)
    assert deal["kind"] == "rookie" and deal["start_year"] == 2025
    years = ct.rookie_years(pid)
    assert deal["years"] == years and deal["pick_number"] == 1
    assert deal["salary"] == ct.rookie_salary(1) == ct.MIN_SALARY
    assert deal["signing_bonus"] == ct.signing_bonus(1)
    v = contract_repo.view(deal, 2026)
    assert (v["year_of"], v["years_left"], v["through"]) == (
        2,
        years - 1,
        2024 + years,
    )


def test_a_signing_bonus_is_paid_once_by_the_drafting_team(env):
    db, factory, league, _, team = env
    pid = factory.rated_player(team, league, status="minors", age=19).id
    _draft(env, pid, pick=1, year=2026)
    repo = ContractRepository(db)
    repo.sign_unsigned(league.id, 2026)
    bonus = ct.signing_bonus(1)
    assert repo.signing_bonuses([team.id], 2026) == {team.id: bonus}
    assert repo.signing_bonuses([team.id], 2027) == {}
    # With the farm: his minor league pay plus the bonus, this season only.
    assert repo.minor_league_pay([team.id], 2026) == {team.id: bonus + ct.MINORS_SALARY}
    # Releasing him doesn't give the bonus back.
    repo.release(pid, team.id, 2026)
    assert repo.signing_bonuses([team.id], 2026) == {team.id: bonus}
    v = contract_repo.view(repo.history(pid)[0], 2026)
    assert v["signing_bonus_text"] == ct.format_salary(bonus)


def test_an_old_draft_pick_signs_a_standard_deal(env):
    db, factory, league, _, team = env
    pid = factory.rated_player(team, league).id
    _draft(env, pid, pick=4, year=2022)  # his rookie deal would be over
    repo = ContractRepository(db)
    repo.sign_unsigned(league.id, 2026)
    assert repo.active(pid, 2026)["kind"] == "standard"


def test_a_rookie_deal_that_runs_out_goes_to_arbitration(env):
    db, factory, league, _, team = env
    pid = factory.rated_player(team, league, status="minors", age=19, level=70).id
    _draft(env, pid, pick=3, year=2026)
    repo = ContractRepository(db)
    repo.sign_unsigned(league.id, 2026)
    end = 2026 + ct.rookie_years(pid)  # first season after his rookie deal
    assert repo.active(pid, end - 1)["kind"] == "rookie"
    assert repo.active(pid, end) is None
    assert repo.sign_unsigned(league.id, end) == 1
    new = repo.active(pid, end)
    assert new["kind"] == "arbitration" and new["start_year"] == end
    assert new["years"] == 1
    assert len(repo.history(pid)) == 2
    # Each arbitration season pays a bigger share, then he's on the market.
    year = end
    while year - 2026 + 1 < 6:
        year += 1
        repo.sign_unsigned(league.id, year)
        assert repo.active(pid, year)["kind"] == "arbitration"
    repo.sign_unsigned(league.id, year + 1)
    assert repo.active(pid, year + 1)["kind"] == "standard"


def test_a_starting_player_never_goes_to_arbitration(env):
    db, factory, league, _, team = env
    pid = factory.rated_player(team, league).id
    repo = ContractRepository(db)
    repo.sign_unsigned(league.id, 2026)
    first = repo.active(pid, 2026)
    after = first["start_year"] + first["years"]
    repo.sign_unsigned(league.id, after)
    assert repo.active(pid, after)["kind"] == "standard"


def test_free_agents_go_unsigned_and_payroll_counts_the_roster(env):
    db, factory, league, _, team = env
    on = factory.rated_player(team, league).id
    gone = factory.rated_player(team, league, status="free_agent").id
    repo = ContractRepository(db)
    repo.sign_unsigned(league.id, 2026)
    assert repo.active(gone, 2026) is None
    assert repo.payroll(team.id, 2026) == repo.active(on, 2026)["salary"]
    assert repo.current_year(league.id) == 2026
