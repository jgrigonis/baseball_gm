# tests/api/test_happiness_repo.py
"""Player moods in the database: the weekly update, trade requests, players
who bench themselves, and what re-signing does
(src/db/repositories/happiness_repo.py)."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.db.repositories.happiness_repo import HappinessRepository
from src.db.repositories.news_repo import NewsRepository
from src.player import happiness as hp


@pytest.fixture
def lg(db_conn, factory):
    league = factory.league(state="season", mode="blitz")
    season = factory.season(year=2025)
    factory.league_season(league, season)
    a = factory.team(city="London", mascot="Lions")
    b = factory.team(city="Tokyo", mascot="Samurai")
    for t in (a, b):
        factory.league_season_team(league, season, t)
    factory.gm(team=a, league=league, is_ai=False)
    factory.gm(team=b, league=league, is_ai=True)
    players = {
        t.id: [factory.rated_player(t, league, 50 + i) for i in range(10)]
        for t in (a, b)
    }
    # London has won 8 of 10.
    for day in range(1, 11):
        db_conn.execute(
            """INSERT INTO games (id, game_date, season_id, home_team_id,
                   away_team_id, completed, winner_id)
               VALUES (%s, %s, %s, %s, %s, 1, %s)""",
            (
                factory._id(),
                f"2025-04-{day:02d}",
                season.id,
                a.id,
                b.id,
                a.id if day <= 8 else b.id,
            ),
        )
    return SimpleNamespace(
        db=db_conn, league=league, season=season, a=a, b=b, players=players
    )


def _repo(lg):
    return HappinessRepository(lg.db, lg.league.id)


def test_every_rostered_player_gets_a_mood(lg):
    n = _repo(lg).update(lg.season.id, date(2025, 4, 11))
    assert n == 20
    row = _repo(lg).mood(lg.players[lg.a.id][0].id, lg.season.id)
    assert -1 <= row["mood"] <= 1
    assert set(row["detail"]["drives"]) == set(hp.DRIVES)
    # Winning 8 of 10 pleases; losing 8 of 10 doesn't.
    win = row["detail"]["drives"]["winning"][0]
    lose = _repo(lg).mood(lg.players[lg.b.id][0].id, lg.season.id)["detail"]["drives"][
        "winning"
    ][0]
    assert win > 0 > lose


def test_moods_update_once_a_week(lg):
    repo = _repo(lg)
    assert repo.update_if_due(lg.season.id, date(2025, 4, 11))
    assert not repo.update_if_due(lg.season.id, date(2025, 4, 15))
    assert repo.update_if_due(lg.season.id, date(2025, 4, 18))


def test_an_unhappy_player_asks_for_a_trade_and_it_makes_the_news(lg):
    pid = lg.players[lg.a.id][0].id
    with (
        patch.object(hp, "target", return_value=-1.0),
        patch.object(hp, "asks_for_trade", side_effect=lambda m, w, t, r: True),
    ):
        _repo(lg).update(lg.season.id, date(2025, 4, 11))
    repo = _repo(lg)
    assert pid in repo.trade_requests([pid])
    assert repo.badges([pid])[pid]["wants_trade"]
    feed = NewsRepository(lg.db).feed(lg.league.id)
    assert any("asks the" in s["headline"] and pid in s["player_ids"] for s in feed)


def test_a_traded_player_drops_his_request(lg):
    pid = lg.players[lg.a.id][0].id
    with (
        patch.object(hp, "target", return_value=-1.0),
        patch.object(hp, "asks_for_trade", side_effect=lambda m, w, t, r: True),
    ):
        _repo(lg).update(lg.season.id, date(2025, 4, 11))
    lg.db.execute(
        "UPDATE team_players SET team_id = %s WHERE player_id = %s", (lg.b.id, pid)
    )
    assert pid not in _repo(lg).trade_requests([pid])


def test_a_miserable_player_can_sit_out_a_few_days(lg):
    pid = lg.players[lg.a.id][0].id
    with (
        patch.object(hp, "target", return_value=-1.0),
        patch.object(hp, "refuses_to_play", side_effect=lambda m, t, r: 4),
    ):
        _repo(lg).update(lg.season.id, date(2025, 4, 11))
    repo = _repo(lg)
    assert pid in repo.refusing([pid], date(2025, 4, 12))
    assert pid not in repo.refusing([pid], date(2025, 4, 15))
    feed = NewsRepository(lg.db).feed(lg.league.id)
    assert any("refuses to play" in s["headline"] for s in feed)


def test_re_signing_terms_follow_his_mood(lg):
    happy_pid = lg.players[lg.a.id][0].id
    sad_pid = lg.players[lg.a.id][1].id
    _repo(lg).update(lg.season.id, date(2025, 4, 11))
    lg.db.execute(
        "UPDATE player_moods SET mood = CASE player_id WHEN %s THEN 0.8 ELSE -0.9 END"
        " WHERE player_id IN (%s, %s)",
        (happy_pid, happy_pid, sad_pid),
    )
    repo = _repo(lg)
    repo.prepare_resign([happy_pid, sad_pid])
    mult, years, out = repo.resign_terms(happy_pid)
    assert mult <= 1 and years is None and not out
    mult, years, out = repo.resign_terms(sad_pid)
    assert mult > 1 and years == 1 and out
    repo.request_trades([(sad_pid, lg.a.id)], 2025)
    assert sad_pid in repo.trade_requests([sad_pid])
