# tests/api/web/test_trades_tab.py
"""The Trades tab, the offer endpoint, and the 40-man minimum on save."""

import pytest
from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user
from src.api.main import app


@pytest.fixture
def client_for(db_conn, factory):
    def make(mode="blitz", players=0):
        league = factory.league(state="season", mode=mode)
        season = factory.season(year=2025)
        factory.draft(league=league, season=season, state="complete")
        mine = factory.team(city="My", mascot="Team")
        theirs = factory.team(city="AI", mascot="Club")
        for t in (mine, theirs):
            factory.league_season_team(league, season, t)
        gm = factory.gm(team=mine, league=league, is_ai=False)
        factory.gm(team=theirs, league=league, is_ai=True)
        for day, completed in (("2025-04-01", 1), ("2025-04-02", 0), ("2025-04-03", 0)):
            db_conn.execute(
                """INSERT INTO games (id, game_date, season_id, home_team_id,
                                      away_team_id, completed)
                   VALUES (%s, %s, %s, %s, %s, %s)""",
                (factory._id(), day, season.id, mine.id, theirs.id, completed),
            )
        roster = [factory.rated_player(mine, league, 55) for _ in range(players)]
        app.dependency_overrides[get_db] = lambda: db_conn
        app.dependency_overrides[get_current_user] = lambda: {"id": None}
        app.dependency_overrides[get_current_gm] = lambda: {
            "id": gm.id,
            "team_id": mine.id,
        }
        return TestClient(app), league, theirs, roster

    yield make
    app.dependency_overrides.clear()


def test_blitz_has_a_trades_tab(client_for):
    client, league, theirs, _ = client_for("blitz")
    html = client.get(f"/leagues/{league.id}/schedule").text
    assert f'href="/leagues/{league.id}/trades"' in html


def test_speed_blitz_has_no_trades_tab(client_for):
    client, league, _, _ = client_for("speed_blitz")
    html = client.get(f"/leagues/{league.id}/schedule").text
    assert f'href="/leagues/{league.id}/trades"' not in html


def test_the_trades_tab_lists_the_other_teams_and_the_deadline(client_for):
    client, league, theirs, _ = client_for("blitz", players=2)
    html = client.get(f"/leagues/{league.id}/trades").text
    assert "Propose trade" in html
    assert "AI Club" in html
    assert "Trade deadline" in html


def test_another_teams_players_for_the_builder(client_for, factory):
    client, league, theirs, _ = client_for("blitz")
    factory.rated_player(theirs, league, 60, name="Target")
    data = client.get(f"/leagues/{league.id}/trades/team/{theirs.id}").json()
    assert [x["last_name"] for x in data["players"]] == ["Target"]


def test_a_broken_offer_comes_back_with_the_reason(client_for):
    client, league, theirs, _ = client_for("blitz")
    r = client.post(
        f"/leagues/{league.id}/trades",
        json={"to_team_id": theirs.id, "give": [], "get": []},
    )
    assert r.status_code == 422
    assert "at least one player" in r.json()["detail"]


def test_the_40_man_needs_at_least_25(client_for):
    client, league, _, roster = client_for("blitz", players=30)
    ids = [p.id for p in roster]
    r = client.put(f"/leagues/{league.id}/roster/save", json={"forty_man": ids[:24]})
    assert r.status_code == 422
    assert "at least 25" in r.json()["detail"]
    r = client.put(f"/leagues/{league.id}/roster/save", json={"forty_man": ids[:25]})
    assert r.status_code == 200


def test_a_team_with_fewer_than_25_players_can_still_save(client_for):
    client, league, _, roster = client_for("blitz", players=20)
    r = client.put(
        f"/leagues/{league.id}/roster/save", json={"forty_man": [p.id for p in roster]}
    )
    assert r.status_code == 200


def test_single_player_gets_the_stop_for_offers_toggle(client_for, db_conn):
    client, league, _, _ = client_for("blitz")
    html = client.get(f"/leagues/{league.id}/trades").text
    assert "Stop the sim when a team offers me a trade" in html
    r = client.post(
        f"/leagues/{league.id}/trade-settings", json={"stop_for_offers": False}
    )
    assert r.status_code == 200
    assert not db_conn.execute(
        "SELECT stop_for_trade_offers FROM leagues WHERE id = %s", (league.id,)
    ).fetchone()["stop_for_trade_offers"]


def test_an_offer_to_you_shows_with_its_answers_and_a_badge(
    client_for, db_conn, factory
):
    from src.db.repositories.trade_repo import TradeRepository

    client, league, theirs, roster = client_for("blitz", players=1)
    other = factory.rated_player(theirs, league, 60)
    mine = db_conn.execute(
        "SELECT team_id FROM team_players WHERE player_id = %s", (roster[0].id,)
    ).fetchone()["team_id"]
    season_id = db_conn.execute(
        "SELECT season_id FROM games WHERE home_team_id = %s LIMIT 1", (mine,)
    ).fetchone()["season_id"]
    TradeRepository(db_conn).create_offer(
        league.id,
        season_id,
        theirs.id,
        mine,
        None,
        "2025-04-01",
        [(other.id, theirs.id), (roster[0].id, mine)],
    )
    html = client.get(f"/leagues/{league.id}/trades").text
    assert "Offers to you" in html
    for button in ("Accept", "Counter", "Reject"):
        assert f">{button}</button>" in html
    assert 'id="trade-badge"' in html
    assert client.get(f"/leagues/{league.id}/trades/inbox").json() == {"count": 1}
    # Compare all: what you'd get, then what you'd give.
    assert f'compareTrade(["{other.id}"], ["{roster[0].id}"])' in html


def test_trades_with_gm_teams_are_offered(client_for, db_conn):
    client, league, theirs, _ = client_for("blitz")
    db_conn.execute("UPDATE gms SET is_ai = FALSE WHERE team_id = %s", (theirs.id,))
    html = client.get(f"/leagues/{league.id}/trades").text
    assert "AI Club (GM)" in html
    assert "coming soon" not in html


def test_with_pick_trades_on_the_builder_lists_picks(client_for, db_conn):
    client, league, theirs, _ = client_for("blitz", players=2)
    db_conn.execute("UPDATE leagues SET pick_trades = TRUE WHERE id = %s", (league.id,))
    html = client.get(f"/leagues/{league.id}/trades").text
    assert "2026 1st round (My Team)" in html
    assert "players or picks" in html
    data = client.get(f"/leagues/{league.id}/trades/team/{theirs.id}").json()
    picks = [p for p in data["players"] if p["roster_status"] == "pick"]
    assert [p["pick_round"] for p in picks] == [1, 2, 3, 4, 5]


def test_without_pick_trades_there_are_no_picks(client_for):
    client, league, theirs, _ = client_for("blitz", players=2)
    html = client.get(f"/leagues/{league.id}/trades").text
    assert "1st round" not in html
    data = client.get(f"/leagues/{league.id}/trades/team/{theirs.id}").json()
    assert all(p["roster_status"] != "pick" for p in data["players"])


def test_shop_offers_and_the_builder_have_compare_buttons(client_for):
    client, league, _, _ = client_for("blitz", players=2)
    html = client.get(f"/leagues/{league.id}/trades").text
    assert 'onclick="trShopCompare(' in html
    assert 'id="tr-compare"' in html


def test_the_trades_tab_is_there_during_the_draft(client_for, db_conn):
    """The offseason trade window is open through the draft, so the tab (and
    the player panel's Shop him, which opens it) works before the draft is
    done."""
    client, league, _, _ = client_for("blitz")
    db_conn.execute("UPDATE leagues SET state = 'draft' WHERE id = %s", (league.id,))
    db_conn.execute(
        "UPDATE drafts SET state = 'pending' WHERE league_id = %s", (league.id,)
    )
    html = client.get(f"/leagues/{league.id}/roster").text
    assert f'href="/leagues/{league.id}/trades"' in html


def test_you_give_can_filter_to_players_who_want_a_trade(client_for, db_conn):
    client, league, _, roster = client_for("blitz", players=2)
    unhappy = roster[0]
    season_id = db_conn.execute(
        "SELECT season_id FROM league_season_teams WHERE league_id = %s LIMIT 1",
        (league.id,),
    ).fetchone()["season_id"]
    team_id = db_conn.execute(
        "SELECT team_id FROM team_players WHERE player_id = %s", (unhappy.id,)
    ).fetchone()["team_id"]
    db_conn.execute(
        """INSERT INTO player_moods (player_id, season_id, league_id, team_id,
                                     mood, target, detail, updated_on,
                                     trade_request_on)
           VALUES (%s, %s, %s, %s, -0.8, -0.8, '{}', '2025-04-01',
                   '2025-04-01')""",
        (unhappy.id, season_id, league.id, team_id),
    )
    html = client.get(f"/leagues/{league.id}/trades").text
    assert "trTradeFilter()" in html
    assert f'"player_id": "{unhappy.id}"' in html
    wants = html.split(f'"player_id": "{unhappy.id}"', 1)[1].split("}", 1)[0]
    assert '"wants_trade": true' in wants
