# tests/api/test_waivers.py
"""Waivers and the salary offset (src/api/services/waivers.py,
free agency phase 2)."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.api.services import free_agents, waivers
from src.api.services.free_agents import FreeAgentError
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
    good = factory.team(city="Good", mascot="Club")
    bad = factory.team(city="Bad", mascot="Club")
    for t in (mine, good, bad):
        factory.league_season_team(league, season, t)
    gm = factory.gm(team=mine, league=league, is_ai=False)
    for t in (good, bad):
        factory.gm(team=t, league=league, is_ai=True)
    for day in GAME_DAYS:
        db_conn.execute(
            """INSERT INTO games (id, game_date, season_id, home_team_id,
                                  away_team_id, completed)
               VALUES (%s, %s, %s, %s, %s, 0)""",
            (factory._id(), day, season.id, good.id, bad.id),
        )
    # Plenty of room under every owner's limits.
    budgets = BudgetRepository(db_conn)
    budgets.for_league(league.id, 2026)
    return SimpleNamespace(
        db=db_conn,
        factory=factory,
        league=league,
        season=season,
        mine=mine,
        good=good,
        bad=bad,
        gm=gm,
        contracts=ContractRepository(db_conn),
        status=PlayerStatusRepository(db_conn),
        waivers=WaiverRepository(db_conn),
    )


def _released(lg, team=None, **kw):
    """A 40-man player released by `team` (mine by default), after a game
    that guaranteed his deal."""
    team = team or lg.mine
    pid = lg.factory.rated_player(team, lg.league, level=65, **kw).id
    lg.contracts.sign_unsigned(lg.league.id, 2026)
    lg.contracts.guarantee_teams([team.id])
    free_agents.release(lg.db, lg.league.id, team.id, pid)
    return pid


@pytest.fixture(autouse=True)
def roomy_owners(monkeypatch):
    monkeypatch.setattr(BudgetRepository, "refusal", lambda *a, **k: None)


def test_a_released_40_man_player_goes_on_waivers(lg):
    pid = _released(lg)
    w = waivers.on_waivers(lg.db, pid)
    assert w["from_team_id"] == lg.mine.id
    # Two sim periods of one day each: after the second game day ahead.
    assert w["clears_on"] == GAME_DAYS[1]
    with pytest.raises(FreeAgentError, match="on waivers"):
        free_agents.sign(lg.db, lg.league.id, lg.good.id, pid)


def test_a_released_minors_player_skips_waivers(lg):
    pid = _released(lg, status="minors")
    assert waivers.on_waivers(lg.db, pid) is None


def test_a_claim_takes_over_his_whole_deal(lg):
    pid = _released(lg)
    deal = lg.contracts.released_deal(pid, lg.mine.id)
    assert lg.contracts.dead_money(lg.mine.id, 2026) == deal["salary"]

    waivers.claim(lg.db, lg.league.id, lg.good.id, pid, 2026)
    assert waivers.after_day(lg.db, lg.league.id, GAME_DAYS[0]) == 0  # not yet
    assert waivers.after_day(lg.db, lg.league.id, GAME_DAYS[1]) == 1

    # An AI claimer puts him on its roster rather than leaving him down.
    assert lg.status.get_status(pid) in ("26man", "40man")
    assert pid in PlayerRepository(lg.db).get_player_ids_from_team_players(lg.good.id)
    now = lg.contracts.active(pid, 2026)
    assert (now["id"], now["team_id"]) == (deal["id"], lg.good.id)
    assert lg.contracts.dead_money(lg.mine.id, 2026) == 0
    assert waivers.on_waivers(lg.db, pid) is None


def test_the_worst_record_wins_the_claim(lg, monkeypatch):
    pid = _released(lg)
    monkeypatch.setattr(
        waivers, "_records", lambda *a: {lg.good.id: 0.6, lg.bad.id: 0.4}
    )
    for t in (lg.good, lg.bad):
        waivers.claim(lg.db, lg.league.id, t.id, pid, 2026)
    waivers.clear_all(lg.db, lg.league.id)
    assert pid in PlayerRepository(lg.db).get_player_ids_from_team_players(lg.bad.id)


def test_you_cant_claim_your_own_player(lg):
    pid = _released(lg)
    with pytest.raises(waivers.WaiverError):
        waivers.claim(lg.db, lg.league.id, lg.mine.id, pid, 2026)


def test_unclaimed_he_clears_to_free_agency_and_the_offset_applies(lg):
    pid = _released(lg)
    owed = lg.contracts.dead_money(lg.mine.id, 2026)
    waivers.after_day(lg.db, lg.league.id, GAME_DAYS[1])
    assert waivers.on_waivers(lg.db, pid) is None
    assert lg.status.get_status(pid) == "free_agent"

    free_agents.sign(lg.db, lg.league.id, lg.good.id, pid)
    new = lg.contracts.active(pid, 2026)["salary"]
    # Full offset: his new salary comes off what I still owe.
    assert lg.contracts.dead_money(lg.mine.id, 2026) == max(0, owed - new)


def test_with_too_few_game_days_left_he_clears_when_the_phase_ends(lg):
    lg.db.execute(
        "UPDATE games SET completed = 1 WHERE season_id = %s AND game_date > %s",
        (lg.season.id, GAME_DAYS[0]),
    )
    pid = _released(lg)
    assert waivers.on_waivers(lg.db, pid)["clears_on"] is None
    assert waivers.after_day(lg.db, lg.league.id, "2026-09-30") == 0
    waivers.clear_all(lg.db, lg.league.id)
    assert waivers.on_waivers(lg.db, pid) is None


def test_a_claim_that_no_longer_fits_passes_to_the_next_team(lg, monkeypatch):
    pid = _released(lg)
    monkeypatch.setattr(
        waivers, "_records", lambda *a: {lg.good.id: 0.6, lg.bad.id: 0.4}
    )
    for t in (lg.good, lg.bad):
        waivers.claim(lg.db, lg.league.id, t.id, pid, 2026)
    monkeypatch.setattr(
        waivers,
        "_why_not",
        lambda conn, league_id, team_id, deal, year: (
            "full" if team_id == lg.bad.id else None
        ),
    )
    waivers.clear_all(lg.db, lg.league.id)
    assert pid in PlayerRepository(lg.db).get_player_ids_from_team_players(lg.good.id)


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


def test_the_tab_shows_waivers_and_claims_work(lg, client):
    pid = _released(lg, team=lg.good, name="Waived")
    html = client.get(f"/leagues/{lg.league.id}/free-agents").text
    assert "1 on waivers" in html
    assert '"clears_text": "Clears after the games on 2026-04-03"' in html

    r = client.get(f"/leagues/{lg.league.id}/waivers/{pid}/claim")
    assert r.status_code == 200 and r.json()["years_left"] >= 1
    assert (
        client.post(f"/leagues/{lg.league.id}/waivers/{pid}/claim").status_code == 200
    )
    assert lg.waivers.claims_by(lg.league.id, lg.mine.id) == {pid}
    html = client.get(f"/leagues/{lg.league.id}/free-agents").text
    assert '"claimed": true' in html
    client.post(f"/leagues/{lg.league.id}/waivers/{pid}/withdraw")
    assert lg.waivers.claims_by(lg.league.id, lg.mine.id) == set()

    html = client.get(f"/leagues/{lg.league.id}/players/{pid}/panel").text
    assert "claimWaiver(" in html


def test_the_release_preview_says_when_he_goes_on_waivers(lg, client):
    up = lg.factory.rated_player(lg.mine, lg.league).id
    down = lg.factory.rated_player(lg.mine, lg.league, status="minors").id
    lg.contracts.sign_unsigned(lg.league.id, 2026)
    base = f"/leagues/{lg.league.id}/players"
    assert client.get(f"{base}/{up}/release").json()["waivers"] is True
    assert client.get(f"{base}/{down}/release").json()["waivers"] is False


# ── News (Josh, 2026-11-11: "I don't even know who got him") ─────────────────


def _stories(lg, prefix):
    rows = lg.db.execute(
        """SELECT headline, body, team_ids, player_ids FROM league_news
           WHERE league_id = %s AND key LIKE %s ORDER BY id""",
        (lg.league.id, prefix + "%"),
    ).fetchall()
    return [dict(r) for r in rows]


def test_a_claim_of_a_persons_released_player_makes_the_news(lg):
    pid = _released(lg)
    assert len(_stories(lg, "fa-release:")) == 1
    for t in (lg.good, lg.bad):
        waivers.claim(lg.db, lg.league.id, t.id, pid, 2026)
    waivers.after_day(lg.db, lg.league.id, GAME_DAYS[1])
    [story] = _stories(lg, "fa-claim:")
    assert "claim" in story["headline"] and "off waivers" in story["headline"]
    assert "1 other team put in a claim" in story["body"]
    assert lg.mine.id in story["team_ids"] and pid in story["player_ids"]


def test_nobody_claiming_a_persons_player_makes_the_news(lg):
    _released(lg)
    waivers.after_day(lg.db, lg.league.id, GAME_DAYS[1])
    [story] = _stories(lg, "fa-cleared:")
    assert "clears waivers" in story["headline"]
    assert "free agent" in story["body"]


def test_signing_a_persons_released_player_makes_the_news(lg):
    pid = _released(lg)
    waivers.after_day(lg.db, lg.league.id, GAME_DAYS[1])
    free_agents.sign(lg.db, lg.league.id, lg.good.id, pid)
    [story] = _stories(lg, "fa-sign-now:")
    assert "sign free agent" in story["headline"]
    assert "released him" in story["body"]
    assert set(story["team_ids"]) == {lg.good.id, lg.mine.id}


def test_a_person_claiming_keeps_him_in_the_minors(lg):
    pid = _released(lg, team=lg.good)
    waivers.claim(lg.db, lg.league.id, lg.mine.id, pid, 2026)
    waivers.after_day(lg.db, lg.league.id, GAME_DAYS[1])
    assert lg.status.get_status(pid) == "minors"


def test_a_fringe_ai_release_stays_out_of_the_news(lg, monkeypatch):
    from src.api.services.news import moves

    monkeypatch.setattr(moves, "shown_grade", lambda p: "D")
    pid = _released(lg, team=lg.good)
    waivers.after_day(lg.db, lg.league.id, GAME_DAYS[1])
    assert waivers.on_waivers(lg.db, pid) is None
    assert _stories(lg, "fa-") == []


def test_other_people_hear_when_a_person_releases_a_good_player(lg, monkeypatch):
    from src.api.services.injury_news import take_injury_news
    from src.api.services.news import moves

    monkeypatch.setattr(moves, "shown_grade", lambda p: "B+")
    lg.db.execute(
        "UPDATE gms SET is_ai = false WHERE league_id = %s AND team_id = %s",
        (lg.league.id, lg.bad.id),
    )
    other = lg.db.execute(
        "SELECT id FROM gms WHERE league_id = %s AND team_id = %s",
        (lg.league.id, lg.bad.id),
    ).fetchone()["id"]
    _released(lg)
    [note] = take_injury_news(lg.db, other)["waivers"]
    assert "B+" in note["text"] and "on waivers until after the games" in note["text"]
    assert not note["text"].startswith("The ") and "the The" not in note["text"]
    assert take_injury_news(lg.db, lg.gm.id)["waivers"] == []


def test_nobody_hears_about_a_fringe_release(lg, monkeypatch):
    from src.api.services.injury_news import take_injury_news
    from src.api.services.news import moves

    monkeypatch.setattr(moves, "shown_grade", lambda p: "C")
    lg.db.execute(
        "UPDATE gms SET is_ai = false WHERE league_id = %s AND team_id = %s",
        (lg.league.id, lg.bad.id),
    )
    other = lg.db.execute(
        "SELECT id FROM gms WHERE league_id = %s AND team_id = %s",
        (lg.league.id, lg.bad.id),
    ).fetchone()["id"]
    _released(lg)
    assert take_injury_news(lg.db, other)["waivers"] == []
