# tests/league/test_trade_deadline.py
"""When the trade window is open, and the sim stopping at the deadline or for
a trade offer."""

from types import SimpleNamespace
from unittest.mock import patch

from src.api.services import sim_next
from src.db.repositories.trade_repo import TradeRepository
from src.league import trade_deadline
from src.league.trade_deadline import _nearest_series_end


def _series(start_day, opponent, games):
    return [(f"2025-{start_day + i:03d}", opponent) for i in range(games)]


def test_the_deadline_is_the_end_of_the_series_nearest_game_108():
    # 3-game series: they end at games 3, 6, ... 108 is a series end.
    games = []
    for n in range(54):
        games += _series(n * 3, f"opp{n % 2}", 3)
    assert _nearest_series_end(games) == games[107][0]


def test_with_uneven_series_it_picks_the_nearest_end():
    # Series of 4: ends at 104 and 108; of 5: ends at 105 and 110.
    games = []
    for n in range(40):
        games += _series(n * 5, f"opp{n % 2}", 5)
    assert _nearest_series_end(games) == games[109][0]


def test_the_last_series_never_counts():
    games = _series(0, "a", 3) + _series(3, "b", 3)
    assert _nearest_series_end(games) == games[2][0]


def test_no_games_no_deadline():
    assert _nearest_series_end([]) is None


def _season_with_games(db, factory, played_through=None):
    league = factory.league(state="season", mode="blitz")
    season = factory.season(year=2025)
    factory.league_season(league, season)
    a, b, c = factory.team(), factory.team(), factory.team()
    days = [("2025-04-01", b), ("2025-04-02", b), ("2025-04-03", c), ("2025-04-04", c)]
    for day, opp in days:
        db.execute(
            """INSERT INTO games (id, game_date, season_id, home_team_id,
                                  away_team_id, completed)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                factory._id(),
                day,
                season.id,
                a.id,
                opp.id,
                int(played_through is not None and day <= played_through),
            ),
        )
    return league, season


def test_window_is_open_until_deadline_days_games_are_followed_by_more(
    db_conn, factory
):
    league, season = _season_with_games(db_conn, factory)
    league_row = {"mode": "blitz", "state": "season"}
    w = trade_deadline.window(db_conn, league_row, season.id)
    assert w == {
        "enabled": True,
        "deadline": "2025-04-02",
        "open": True,
        "deadline_day": False,
    }


def test_deadline_day_is_still_open(db_conn, factory):
    _, season = _season_with_games(db_conn, factory, played_through="2025-04-02")
    w = trade_deadline.window(db_conn, {"mode": "blitz", "state": "season"}, season.id)
    assert w["open"] and w["deadline_day"]


def test_after_the_deadline_it_is_closed(db_conn, factory):
    _, season = _season_with_games(db_conn, factory, played_through="2025-04-03")
    w = trade_deadline.window(db_conn, {"mode": "blitz", "state": "season"}, season.id)
    assert not w["open"]


def test_modes_without_trades_never_open(db_conn, factory):
    _, season = _season_with_games(db_conn, factory)
    for mode in ("speed_blitz", "longform"):
        w = trade_deadline.window(db_conn, {"mode": mode, "state": "season"}, season.id)
        assert not w["enabled"] and not w["open"]


def test_the_playoffs_are_closed(db_conn, factory):
    _, season = _season_with_games(db_conn, factory)
    w = trade_deadline.window(
        db_conn, {"mode": "blitz", "state": "playoffs"}, season.id
    )
    assert not w["open"]


class TestSimStopsAtTheDeadline:
    def _sim(self, db, factory, mode, count):
        league, season = _season_with_games(db, factory)
        db.execute("UPDATE leagues SET mode = %s WHERE id = %s", (mode, league.id))
        dates = iter(["2025-04-01", "2025-04-02", "2025-04-03", "2025-04-04"])

        def one_day(league_id, conn):
            d = next(dates)
            conn.execute(
                "UPDATE games SET completed = 1 WHERE season_id = %s AND game_date = %s",
                (season.id, d),
            )
            return {"game_date": d, "games_played": 1}

        with patch.object(sim_next, "sim_next_day", side_effect=one_day) as day:
            summary = sim_next.sim_days(league.id, db, count)
        return summary, day.call_count

    def test_a_long_sim_stops_after_deadline_day(self, db_conn, factory):
        summary, days = self._sim(db_conn, factory, "blitz", "season")
        assert days == 2
        assert summary["trade_deadline"] is True
        assert summary["last_date"] == "2025-04-02"

    def test_speed_blitz_plays_straight_through(self, db_conn, factory):
        summary, days = self._sim(db_conn, factory, "speed_blitz", 3)
        assert days == 3
        assert summary["trade_deadline"] is False


class TestSimStopsForAnOffer:
    """Single player: with stop_for_trade_offers on, a sim stops the day an
    offer arrives for the GM."""

    def _sim(self, db, factory, stop=True, humans=1):
        league, season = _season_with_games(db, factory)
        db.execute(
            "UPDATE leagues SET stop_for_trade_offers = %s WHERE id = %s",
            (stop, league.id),
        )
        teams = db.execute(
            "SELECT DISTINCT home_team_id, away_team_id FROM games WHERE season_id = %s",
            (season.id,),
        ).fetchall()
        mine = SimpleNamespace(id=teams[0]["home_team_id"])
        other = teams[0]["away_team_id"]
        factory.gm(team=mine, league=league, is_ai=False)
        for _ in range(humans - 1):
            factory.gm(league=league, is_ai=False)
        # Human GMs are only counted once they have a user.
        for g in db.execute(
            "SELECT id FROM gms WHERE league_id = %s AND NOT is_ai", (league.id,)
        ).fetchall():
            db.execute(
                "INSERT INTO users (id, session_token, display_name) VALUES (%s, %s, 'x')",
                (g["id"], g["id"]),
            )
            db.execute("UPDATE gms SET user_id = id WHERE id = %s", (g["id"],))
        dates = iter(["2025-04-01", "2025-04-02", "2025-04-03", "2025-04-04"])

        def one_day(league_id, conn):
            d = next(dates)
            if d == "2025-04-01":
                TradeRepository(conn).create_offer(
                    league_id, season.id, other, mine.id, None, d, []
                )
            return {"game_date": d, "games_played": 1}

        with patch.object(sim_next, "sim_next_day", side_effect=one_day) as day:
            summary = sim_next.sim_days(league.id, db, 2)
        return summary, day.call_count

    def test_the_sim_stops_the_day_an_offer_arrives(self, db_conn, factory):
        summary, days = self._sim(db_conn, factory)
        assert days == 1
        assert summary["trade_offer"] is True

    def test_with_the_toggle_off_it_plays_on(self, db_conn, factory):
        summary, days = self._sim(db_conn, factory, stop=False)
        assert days == 2
        assert summary["trade_offer"] is False

    def test_multiplayer_sims_never_stop_for_offers(self, db_conn, factory):
        summary, days = self._sim(db_conn, factory, humans=2)
        assert days == 2
