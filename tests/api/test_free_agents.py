# tests/api/test_free_agents.py
"""Releasing players and signing free agents (src/api/services/free_agents.py,
src/db/repositories/contract_repo.py), and the Free Agents tab."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.services import free_agents, waivers
from src.api.services.free_agents import FreeAgentError
from src.db.repositories.contract_repo import ContractRepository
from src.db.repositories.player_repo import PlayerRepository
from src.db.repositories.player_status_repo import PlayerStatusRepository
from src.db.repositories.trade_repo import TradeRepository


@pytest.fixture
def lg(db_conn, factory):
    league = factory.league(state="season", mode="blitz")
    season = factory.season(year=2026)
    factory.league_season(league, season)
    mine = factory.team(city="My", mascot="Team")
    theirs = factory.team(city="AI", mascot="Club")
    for t in (mine, theirs):
        factory.league_season_team(league, season, t)
    gm = factory.gm(team=mine, league=league, is_ai=False)
    factory.gm(team=theirs, league=league, is_ai=True)
    db_conn.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id,
                              away_team_id, completed)
           VALUES (%s, '2026-04-02', %s, %s, %s, 0)""",
        (factory._id(), season.id, mine.id, theirs.id),
    )
    # A roomy cap, so the owner's hard limit (tests/api/test_budgets.py)
    # doesn't stop these signings.
    for t in (mine, theirs):
        db_conn.execute(
            """INSERT INTO team_budgets (league_id, team_id, year, cap, budget)
               VALUES (%s, %s, 2026, 900000000, 900000000)""",
            (league.id, t.id),
        )
    return SimpleNamespace(
        db=db_conn,
        factory=factory,
        league=league,
        season=season,
        mine=mine,
        theirs=theirs,
        gm=gm,
        contracts=ContractRepository(db_conn),
        status=PlayerStatusRepository(db_conn),
    )


def _signed(lg, **kw):
    """A player on my team with his deal for 2026."""
    pid = lg.factory.rated_player(lg.mine, lg.league, **kw).id
    lg.contracts.sign_unsigned(lg.league.id, 2026)
    return pid


def _years_left(deal, year):
    return deal["start_year"] + deal["years"] - year


# ── Guaranteed money ──────────────────────────────────────────────────────────


def test_a_40_man_players_deal_is_guaranteed_and_a_minors_ones_isnt(lg):
    up = _signed(lg, level=60)
    down = _signed(lg, level=60, status="minors")
    deals = lg.contracts.active_for([up, down], 2026)
    assert deals[up]["guaranteed"] and not deals[down]["guaranteed"]
    # Payroll is guaranteed money only.
    assert lg.contracts.payroll(lg.mine.id, 2026) == deals[up]["salary"]


def test_moving_up_to_the_40_man_guarantees_the_deal(lg):
    pid = _signed(lg, status="minors")
    lg.status.set_status(pid, "40man")
    assert lg.contracts.active(pid, 2026)["guaranteed"]
    # It stays guaranteed when he goes back down.
    lg.status.bulk_set({pid: "minors"})
    assert lg.contracts.active(pid, 2026)["guaranteed"]


# ── Release ───────────────────────────────────────────────────────────────────


def test_releasing_a_40_man_player_leaves_dead_money(lg):
    pid = _signed(lg, level=70)
    deal = lg.contracts.active(pid, 2026)
    left = _years_left(deal, 2026)

    owed = free_agents.release(lg.db, lg.league.id, lg.mine.id, pid)

    assert owed["salary"] == deal["salary"]
    assert owed["seasons"] == left
    assert owed["total"] == deal["salary"] * left
    assert lg.status.get_status(pid) == "free_agent"
    assert pid not in PlayerRepository(lg.db).get_player_ids_from_team_players(
        lg.mine.id
    )
    # The deal is no longer his, but the team still pays it.
    assert lg.contracts.active(pid, 2026) is None
    assert lg.contracts.dead_money(lg.mine.id, 2026) == deal["salary"]
    assert lg.contracts.payroll(lg.mine.id, 2026) == deal["salary"]
    last = deal["start_year"] + deal["years"] - 1
    assert lg.contracts.dead_money(lg.mine.id, last) == deal["salary"]
    assert lg.contracts.dead_money(lg.mine.id, last + 1) == 0


def test_releasing_a_minors_player_is_free(lg):
    pid = _signed(lg, status="minors")
    assert (
        free_agents.release_preview(lg.db, lg.league.id, lg.mine.id, pid)["total"] == 0
    )
    owed = free_agents.release(lg.db, lg.league.id, lg.mine.id, pid)
    assert owed["total"] == 0
    assert lg.contracts.dead_money(lg.mine.id, 2026) == 0


def test_the_preview_matches_what_the_release_costs(lg):
    pid = _signed(lg, level=65)
    preview = free_agents.release_preview(lg.db, lg.league.id, lg.mine.id, pid)
    owed = free_agents.release(lg.db, lg.league.id, lg.mine.id, pid)
    assert preview["total"] == owed["total"] > 0
    assert preview["total_text"]


def test_you_cant_release_someone_elses_player(lg):
    pid = lg.factory.rated_player(lg.theirs, lg.league).id
    with pytest.raises(FreeAgentError):
        free_agents.release(lg.db, lg.league.id, lg.mine.id, pid)


def test_a_released_player_leaves_the_rotation_and_trade_offers(lg):
    pid = _signed(lg, pitcher=True)
    lg.db.execute(
        """INSERT INTO team_rotations (team_id, season_id, player_id,
                                       rotation_order, effective_date)
           VALUES (%s, %s, %s, 1, '2026-04-01')""",
        (lg.mine.id, lg.season.id, pid),
    )
    their = lg.factory.rated_player(lg.theirs, lg.league).id
    offer_id = TradeRepository(lg.db).create_offer(
        lg.league.id,
        lg.season.id,
        lg.mine.id,
        lg.theirs.id,
        lg.gm.id,
        "2026-04-01",
        [(pid, lg.mine.id), (their, lg.theirs.id)],
    )
    free_agents.release(lg.db, lg.league.id, lg.mine.id, pid)
    row = lg.db.execute(
        "SELECT end_date FROM team_rotations WHERE player_id = %s", (pid,)
    ).fetchone()
    assert row["end_date"] == "2026-04-02"
    assert TradeRepository(lg.db).get(offer_id)["status"] == "void"


def test_nothing_moves_in_a_finished_league(lg):
    pid = _signed(lg)
    lg.db.execute(
        "UPDATE leagues SET state = 'complete' WHERE id = %s", (lg.league.id,)
    )
    with pytest.raises(FreeAgentError):
        free_agents.release(lg.db, lg.league.id, lg.mine.id, pid)


# ── Signing ───────────────────────────────────────────────────────────────────


def test_signing_a_free_agent_at_his_asking_price(lg):
    pid = lg.factory.rated_player(lg.theirs, lg.league, level=62).id
    lg.contracts.sign_unsigned(lg.league.id, 2026)
    free_agents.release(lg.db, lg.league.id, lg.theirs.id, pid)
    waivers.clear_all(lg.db, lg.league.id)  # nobody claimed him

    result = free_agents.sign(lg.db, lg.league.id, lg.mine.id, pid)

    record = PlayerRepository(lg.db).look_up(pid)
    ask = free_agents.asking_deal(record, 2026)
    deal = lg.contracts.active(pid, 2026)
    assert (deal["salary"], deal["years"], deal["start_year"]) == (
        ask.salary,
        ask.years,
        2026,
    )
    assert deal["guaranteed"] and deal["team_id"] == lg.mine.id
    assert result["years"] == ask.years
    assert lg.status.get_status(pid) == "minors"
    assert pid in PlayerRepository(lg.db).get_player_ids_from_team_players(lg.mine.id)
    # His old team still pays his old deal; his new one is on my payroll.
    assert lg.contracts.dead_money(lg.theirs.id, 2026) > 0
    assert lg.contracts.payroll(lg.mine.id, 2026) == ask.salary


def test_only_free_agents_can_be_signed(lg):
    pid = lg.factory.rated_player(lg.theirs, lg.league).id
    with pytest.raises(FreeAgentError):
        free_agents.sign(lg.db, lg.league.id, lg.mine.id, pid)


def test_a_full_minors_has_to_release_first(lg, monkeypatch):
    monkeypatch.setattr(free_agents, "MINORS_LIMIT", 1)
    lg.factory.rated_player(lg.mine, lg.league, status="minors")
    pid = lg.factory.rated_player(lg.theirs, lg.league, status="free_agent").id
    lg.db.execute("DELETE FROM team_players WHERE player_id = %s", (pid,))
    with pytest.raises(FreeAgentError, match="Release someone first"):
        free_agents.sign(lg.db, lg.league.id, lg.mine.id, pid)


def test_the_asking_price_holds_all_season(lg):
    pid = lg.factory.rated_player(lg.mine, lg.league, level=60).id
    record = PlayerRepository(lg.db).look_up(pid)
    assert free_agents.asking_deal(record, 2026) == free_agents.asking_deal(
        record, 2026
    )


# ── The tab ───────────────────────────────────────────────────────────────────


@pytest.fixture
def client(lg):
    app.dependency_overrides[get_db] = lambda: lg.db
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    me = {"id": lg.gm.id, "team_id": lg.mine.id}
    app.dependency_overrides[get_current_gm] = lambda: me
    app.dependency_overrides[get_gm_or_viewer] = lambda: me
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_the_tab_lists_free_agents_with_their_price(lg, client):
    lg.factory.rated_player(lg.mine, lg.league, level=60, name="Keeper")
    pid = lg.factory.rated_player(
        lg.theirs, lg.league, level=60, status="free_agent", name="Loose"
    ).id
    lg.db.execute("DELETE FROM team_players WHERE player_id = %s", (pid,))
    html = client.get(f"/leagues/{lg.league.id}/free-agents").text
    assert "Free Agents" in html
    assert '"last_name": "Loose"' in html
    assert '"last_name": "Keeper"' not in html
    assert '"salary_text": "$' in html
    assert "Minors 0/120" in html


def test_best_first_follows_the_grade_shown(lg, client):
    import json
    import re

    for i, level in enumerate((40, 55, 70, 85, 50, 65)):
        pid = lg.factory.rated_player(
            lg.theirs,
            lg.league,
            level=level,
            status="free_agent",
            pitcher=bool(i % 2),
        ).id
        lg.db.execute("DELETE FROM team_players WHERE player_id = %s", (pid,))
    html = client.get(f"/leagues/{lg.league.id}/free-agents").text
    players = json.loads(re.search(r"const FA = (\[.*?\]);\n", html).group(1))
    scores = [p["overall_score"] for p in players]
    assert scores == sorted(scores, reverse=True)
    order = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"]
    ranks = [order.index(p["overall"]) for p in players]
    assert ranks == sorted(ranks)


def test_overall_score_never_disagrees_with_the_grade():
    from src.api.grade_curves import overall_score, overall_to_grade

    order = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"]
    pts = [(raw / 2, kind) for raw in range(40, 200) for kind in ("hitter", "pitcher")]
    pts.sort(key=lambda p: -overall_score(*p))
    ranks = [order.index(overall_to_grade(*p)) for p in pts]
    assert ranks == sorted(ranks)


def test_release_and_sign_endpoints(lg, client):
    pid = _signed(lg, level=60)
    r = client.get(f"/leagues/{lg.league.id}/players/{pid}/release")
    assert r.status_code == 200 and r.json()["total"] > 0
    r = client.post(f"/leagues/{lg.league.id}/players/{pid}/release")
    assert r.status_code == 200
    assert lg.status.get_status(pid) == "free_agent"
    # On waivers first; nobody claims him.
    r = client.post(f"/leagues/{lg.league.id}/free-agents/{pid}/sign")
    assert r.status_code == 422 and "waivers" in r.json()["detail"]
    waivers.clear_all(lg.db, lg.league.id)
    r = client.post(f"/leagues/{lg.league.id}/free-agents/{pid}/sign")
    assert r.status_code == 200
    assert lg.status.get_status(pid) == "minors"
    # He can't be signed twice.
    r = client.post(f"/leagues/{lg.league.id}/free-agents/{pid}/sign")
    assert r.status_code == 422


def test_the_panel_offers_release_for_my_player_and_sign_for_a_free_agent(lg, client):
    mine = _signed(lg)
    html = client.get(f"/leagues/{lg.league.id}/players/{mine}/panel").text
    assert "releasePlayer(" in html
    free_agents.release(lg.db, lg.league.id, lg.mine.id, mine)
    html = client.get(f"/leagues/{lg.league.id}/players/{mine}/panel").text
    assert "releasePlayer(" not in html  # on waivers: he was mine
    waivers.clear_all(lg.db, lg.league.id)
    html = client.get(f"/leagues/{lg.league.id}/players/{mine}/panel").text
    assert "signFreeAgent(" in html and "releasePlayer(" not in html


# ── Undrafted players and the next draft ──────────────────────────────────────


def test_unsigned_undrafted_free_agents_go_back_into_the_draft_pool(lg):
    repo = PlayerRepository(lg.db)

    def free_agent(age):
        pid = lg.factory.rated_player(
            lg.theirs, lg.league, status="free_agent", age=age
        ).id
        lg.db.execute("DELETE FROM team_players WHERE player_id = %s", (pid,))
        return pid

    young = free_agent(21)
    old = free_agent(24)
    released = _signed(lg, status="minors", age=21)
    free_agents.release(lg.db, lg.league.id, lg.mine.id, released)

    assert repo.return_undrafted_to_pool(lg.league.id) == 1
    assert lg.status.get_status(young) == "prospect"
    assert lg.status.get_status(old) == "free_agent"  # too old for the draft
    assert lg.status.get_status(released) == "free_agent"  # he signed once

    # Undrafted again: back to free agency.
    assert repo.release_undrafted(lg.league.id) == 1
    assert lg.status.get_status(young) == "free_agent"
