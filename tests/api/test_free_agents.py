# tests/api/test_free_agents.py
"""Releasing players and signing free agents (src/api/services/free_agents.py,
src/db/repositories/contract_repo.py), and the Free Agents tab."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user, get_gm_or_viewer
from src.api.main import app
from src.player import contracts as ct
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


def _signed(lg, played=True, **kw):
    """A player on my team with his deal for 2026, and (played) a game
    since, which guarantees the deals of my 40-man."""
    pid = lg.factory.rated_player(lg.mine, lg.league, **kw).id
    lg.contracts.sign_unsigned(lg.league.id, 2026)
    if played:
        lg.contracts.guarantee_teams([lg.mine.id])
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


def test_moving_up_to_the_40_man_doesnt_guarantee_the_deal_a_game_does(lg):
    pid = _signed(lg, status="minors")
    lg.status.set_status(pid, "40man")
    deal = lg.contracts.active(pid, 2026)
    assert not deal["guaranteed"]
    # On the 40-man he's on the payroll, but releasing him is still free.
    assert deal["on_payroll"]
    assert lg.contracts.release_cost(pid, 2026)["total"] == 0
    # Back down before a game: nothing owed, off the payroll.
    lg.status.bulk_set({pid: "minors"})
    assert not lg.contracts.active(pid, 2026)["on_payroll"]
    # Up again and a game played: guaranteed, and it stays guaranteed when
    # he goes back down.
    lg.status.bulk_set({pid: "40man"})
    lg.contracts.guarantee_teams([lg.mine.id])
    assert lg.contracts.active(pid, 2026)["guaranteed"]
    lg.status.bulk_set({pid: "minors"})
    assert lg.contracts.active(pid, 2026)["guaranteed"]


def test_a_new_40_man_deal_waits_for_a_game(lg):
    pid = _signed(lg, played=False, level=60)
    deal = lg.contracts.active(pid, 2026)
    assert not deal["guaranteed"]
    # Still on the payroll: he's on the 40-man.
    assert lg.contracts.payroll(lg.mine.id, 2026) == deal["salary"]
    owed = free_agents.release(lg.db, lg.league.id, lg.mine.id, pid)
    assert owed["total"] == 0
    assert lg.contracts.dead_money(lg.mine.id, 2026) == 0


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
    lg.contracts.guarantee_teams([lg.theirs.id])  # a game played
    free_agents.release(lg.db, lg.league.id, lg.theirs.id, pid)
    waivers.clear_all(lg.db, lg.league.id)  # nobody claimed him
    owed = lg.contracts.dead_money(lg.theirs.id, 2026)
    assert owed > 0

    result = free_agents.sign(lg.db, lg.league.id, lg.mine.id, pid)

    record = PlayerRepository(lg.db).look_up(pid)
    discount = free_agents.market_discount(lg.db, lg.league.id)
    ask = free_agents.asking_deal(record, 2026, 1.0, discount)
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
    # Full offset: his new salary comes off what his old team still owes;
    # his new deal is on my payroll.
    assert lg.contracts.dead_money(lg.theirs.id, 2026) == max(0, owed - ask.salary)
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


def test_the_asking_price_holds_within_a_step(lg):
    pid = lg.factory.rated_player(lg.mine, lg.league, level=60).id
    record = PlayerRepository(lg.db).look_up(pid)
    assert free_agents.asking_deal(record, 2026) == free_agents.asking_deal(
        record, 2026
    )


def test_unsigned_free_agents_get_cheaper_down_to_half():
    d = free_agents.discount_for
    assert d("offseason", 0) == d("draft", 0) == 1.0
    assert d("preseason", 0) == pytest.approx(0.9)
    assert d("season", 0) == pytest.approx(0.9)
    assert d("season", 6) == pytest.approx(0.9)
    assert d("season", 7) == pytest.approx(0.8)
    assert d("season", 90) == free_agents.MARKET_FLOOR == 0.5


def test_a_discounted_ask_and_a_fringe_ask(lg):
    good = PlayerRepository(lg.db).look_up(
        lg.factory.rated_player(lg.mine, lg.league, level=70).id
    )
    full = free_agents.asking_deal(good, 2026)
    half = free_agents.asking_deal(good, 2026, 1.0, 0.5)
    assert half.years == full.years
    assert half.salary == pytest.approx(full.salary / 2, rel=0.01)
    fringe = PlayerRepository(lg.db).look_up(
        lg.factory.rated_player(lg.mine, lg.league, level=35).id
    )
    assert free_agents.is_fringe(fringe)
    assert free_agents.asking_deal(fringe, 2026) == ct.Deal(
        ct.MIN_SALARY, 1, "standard"
    )


def test_the_discount_follows_days_played(lg):
    assert free_agents.market_discount(lg.db, lg.league.id) == pytest.approx(0.9)
    for day in ("2026-04-02", "2026-04-16"):
        lg.db.execute(
            """INSERT INTO games (id, game_date, season_id, home_team_id,
                                  away_team_id, completed)
               VALUES (%s, %s, %s, %s, %s, 1)""",
            (lg.factory._id(), day, lg.season.id, lg.mine.id, lg.theirs.id),
        )
    # Two weeks in: two more steps off.
    assert free_agents.market_discount(lg.db, lg.league.id) == pytest.approx(0.7)


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


def test_the_offseason_tab_shows_next_seasons_room(lg, client):
    lg.db.execute(
        "UPDATE leagues SET state = 'offseason' WHERE id = %s", (lg.league.id,)
    )
    pid = lg.factory.rated_player(lg.mine, lg.league, level=60, name="Expiring").id
    lg.contracts.insert_deal(
        pid, lg.league.id, lg.mine.id, ct.Deal(5_000_000, 3, "standard"), 2024
    )
    # Its own tab (Josh, 2026-11-10), so the pool's sorts leave it alone.
    assert "fa-expiring" not in client.get(f"/leagues/{lg.league.id}/free-agents").text
    html = client.get(f"/leagues/{lg.league.id}/expiring").text
    assert '<h1 class="page-title">Expiring Deals</h1>' in html
    assert 'id="ex-sort"' in html
    assert f'href="/leagues/{lg.league.id}/expiring"' in html
    assert "Room left next season:" in html
    assert "from their bank to keep your own players." in html
    assert '"fate": "auto"' in html


def test_expiring_rows_show_the_season_line_and_who_is_hurt(lg, client):
    """Josh, 2026-11-09: each expiring row has his season stat line, and an
    injured player shows in red."""
    lg.db.execute(
        "UPDATE leagues SET state = 'offseason' WHERE id = %s", (lg.league.id,)
    )
    bat = lg.factory.rated_player(lg.mine, lg.league, level=60, name="Slugger").id
    arm = lg.factory.rated_player(
        lg.mine, lg.league, level=60, pitcher=True, name="Hurler"
    ).id
    lg.db.execute(
        "UPDATE player_skills SET contact = 10, power = 10, eye = 10, speed = 10,"
        " infield = 10, outfield = 10, catching = 10 WHERE player_id = %s",
        (arm,),
    )
    for pid in (bat, arm):
        lg.contracts.insert_deal(
            pid, lg.league.id, lg.mine.id, ct.Deal(5_000_000, 3, "standard"), 2024
        )
    lg.db.execute(
        """INSERT INTO player_season_stats
             (player_id, season_id, team_id, bat_games_played, bat_ab, bat_hits,
              bat_doubles, bat_triples, bat_home_runs, bat_rbi, bat_walks,
              bat_hbp, bat_sac_flys)
           VALUES (%s, %s, %s, 150, 500, 150, 30, 2, 25, 90, 50, 5, 5)""",
        (bat, lg.season.id, lg.mine.id),
    )
    lg.db.execute(
        """INSERT INTO player_season_stats
             (player_id, season_id, team_id, pitch_games_played,
              pitch_games_started, pitch_outs, pitch_earned_runs,
              pitch_wins, pitch_losses, pitch_saves)
           VALUES (%s, %s, %s, 30, 30, 540, 70, 14, 8, 0)""",
        (arm, lg.season.id, lg.mine.id),
    )
    lg.db.execute(
        "INSERT INTO player_injuries (player_id, league_id, return_date)"
        " VALUES (%s, %s, '2099-01-01')",
        (arm, lg.league.id),
    )
    html = client.get(f"/leagues/{lg.league.id}/expiring").text
    assert '"stat_avg": "0.300"' in html
    assert '"stat_hr": 25' in html
    assert '"stat_rbi": 90' in html
    assert '"stat_ops": ".884"' in html  # .366 OBP + .518 SLG
    assert '"stat_era": "3.50"' in html
    assert '"stat_ip": "180.0"' in html
    assert '"stat_w": 14' in html
    assert '"injured": true' in html
    assert "function seasonLineHtml" in html


def test_a_re_sign_call_returns_every_rows_fate_and_the_room(lg, client):
    lg.db.execute(
        "UPDATE leagues SET state = 'offseason' WHERE id = %s", (lg.league.id,)
    )
    pid = lg.factory.rated_player(lg.mine, lg.league, level=60, name="Expiring").id
    lg.contracts.insert_deal(
        pid, lg.league.id, lg.mine.id, ct.Deal(5_000_000, 3, "standard"), 2024
    )
    r = client.post(
        f"/leagues/{lg.league.id}/players/{pid}/expiring", json={"choice": "let_go"}
    )
    assert r.status_code == 200
    d = r.json()
    assert d["rows"][pid] == {"choice": "let_go", "fate": "go"}
    assert "left_text" in d["money"]


def test_re_sign_all_re_signs_every_expiring_deal(lg, client):
    lg.db.execute(
        "UPDATE leagues SET state = 'offseason' WHERE id = %s", (lg.league.id,)
    )
    ids = []
    for name in ("One", "Two"):
        pid = lg.factory.rated_player(lg.mine, lg.league, level=60, name=name).id
        lg.contracts.insert_deal(
            pid, lg.league.id, lg.mine.id, ct.Deal(5_000_000, 3, "standard"), 2024
        )
        ids.append(pid)
    html = client.get(f"/leagues/{lg.league.id}/expiring").text
    assert 'id="fa-resign-all"' in html
    assert '"count": 2' in html
    r = client.post(f"/leagues/{lg.league.id}/expiring/resign-all")
    assert r.status_code == 200
    d = r.json()
    assert d["count"] == 2
    assert all(d["rows"][pid]["choice"] == "resign" for pid in ids)
    assert d["all"] is None  # nothing left to re-sign


def _icon_seasons(lg, pid, team):
    from src.api.services import icons

    for i in range(icons.ICON_SEASONS):
        s = lg.factory.season(year=2010 + i)
        lg.db.execute(
            """INSERT INTO player_season_stats
                 (player_id, season_id, team_id, bat_games_played)
               VALUES (%s, %s, %s, 100)""",
            (pid, s.id, team.id),
        )


def test_expiring_icons_carry_the_icon_tag(lg, client):
    lg.db.execute(
        "UPDATE leagues SET state = 'offseason' WHERE id = %s", (lg.league.id,)
    )
    star = lg.factory.rated_player(lg.mine, lg.league, level=85, name="Legend").id
    lg.contracts.insert_deal(
        star, lg.league.id, lg.mine.id, ct.Deal(5_000_000, 3, "standard"), 2024
    )
    _icon_seasons(lg, star, lg.mine)
    html = client.get(f"/leagues/{lg.league.id}/expiring").text
    assert '"icon_seasons": 5' in html
    assert "${iconTag(p)}" in html


def test_our_icon_in_the_pool_carries_the_icon_tag(lg, client):
    star = lg.factory.rated_player(
        lg.mine, lg.league, level=85, status="free_agent", name="Legend"
    ).id
    lg.db.execute("DELETE FROM team_players WHERE player_id = %s", (star,))
    _icon_seasons(lg, star, lg.mine)
    html = client.get(f"/leagues/{lg.league.id}/free-agents").text
    assert '"icon_seasons": 5' in html


def test_the_expiring_tab_only_in_the_offseason(lg, client):
    html = client.get(f"/leagues/{lg.league.id}/standings").text
    assert f'href="/leagues/{lg.league.id}/expiring"' not in html
    html = client.get(f"/leagues/{lg.league.id}/expiring").text
    assert "once the champion is crowned" in html
    lg.db.execute(
        "UPDATE leagues SET state = 'offseason' WHERE id = %s", (lg.league.id,)
    )
    html = client.get(f"/leagues/{lg.league.id}/expiring").text
    assert "None of your deals end with this season." in html
