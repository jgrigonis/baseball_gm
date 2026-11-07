# tests/api/test_happiness_repo.py
"""Player moods in the database: the weekly update, trade requests, players
who bench themselves, and what re-signing does
(src/db/repositories/happiness_repo.py)."""

from dataclasses import replace
from datetime import date, timedelta
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


def test_an_unhappy_morale_ruiner_drags_his_teammates_down(lg):
    ruiner = lg.players[lg.a.id][0]
    mate = lg.players[lg.a.id][1]
    rival = lg.players[lg.b.id][0]
    # The clubhouse is the active roster.
    lg.db.execute(
        "UPDATE player_status SET status = '26man' WHERE player_id = ANY(%s)",
        ([ruiner.id, mate.id, rival.id],),
    )
    repo = _repo(lg)
    repo.update(lg.season.id, date(2025, 4, 4))
    before = {
        pid: repo.mood(pid, lg.season.id)["target"] for pid in (mate.id, rival.id)
    }
    lg.db.execute(
        "UPDATE player_moods SET mood = -0.9 WHERE player_id = %s", (ruiner.id,)
    )
    real = hp.personality_for

    def fake(pid):
        p = real(pid)
        traits = {**p.traits, "temper": 90} if pid == mate.id else p.traits
        return hp.Personality(p.type, p.drives, traits, p.climate, pid == ruiner.id)

    lg.db.execute("DELETE FROM player_personality")
    with (
        patch.object(hp, "personality_for", side_effect=fake),
        patch.object(
            hp.Personality, "from_row", side_effect=lambda row: fake(row["player_id"])
        ),
    ):
        _repo(lg).update(lg.season.id, date(2025, 4, 11))
    after = _repo(lg).mood(mate.id, lg.season.id)
    assert after["target"] < before[mate.id] - 0.15
    assert after["detail"]["clubhouse"][1] == ruiner.id
    assert any("souring the clubhouse" in line for line in after["detail"]["lines"])
    # The other team's clubhouse is fine.
    assert "clubhouse" not in _repo(lg).mood(rival.id, lg.season.id)["detail"]


def test_the_roster_badge_counts_the_teams_trade_requests(lg):
    with (
        patch.object(hp, "target", return_value=-1.0),
        patch.object(hp, "asks_for_trade", side_effect=lambda m, w, t, r: True),
    ):
        _repo(lg).update(lg.season.id, date(2025, 4, 11))
    assert _repo(lg).team_trade_requests(lg.a.id) == 10
    pid = lg.players[lg.a.id][0].id
    lg.db.execute(
        "UPDATE team_players SET team_id = %s WHERE player_id = %s", (lg.b.id, pid)
    )
    # Traded away: his request goes with him, and the new team doesn't count it.
    assert _repo(lg).team_trade_requests(lg.a.id) == 9
    assert _repo(lg).team_trade_requests(lg.b.id) == 10
    assert _repo(lg).team_trade_requests(None) == 0


def test_an_elite_coaching_staff_lifts_moods_and_bare_bones_sours_them(lg):
    repo = _repo(lg)
    repo.update(lg.season.id, date(2025, 4, 4))
    before = {
        p.id: repo.mood(p.id, lg.season.id)
        for t in (lg.a, lg.b)
        for p in lg.players[t.id]
    }
    assert all("coaching" not in m["detail"] for m in before.values())
    for team, level in ((lg.a, 4), (lg.b, 0)):
        lg.db.execute(
            """INSERT INTO team_budgets (league_id, team_id, year, cap, budget,
                   coaching)
               VALUES (%s, %s, 2025, 160000000, 160000000, %s)""",
            (lg.league.id, team.id, level),
        )
    # Same day again, so only the coaching has changed.
    repo.update(lg.season.id, date(2025, 4, 4))
    for team, sign in ((lg.a, 1), (lg.b, -1)):
        for p in lg.players[team.id]:
            after = repo.mood(p.id, lg.season.id)
            lift = after["detail"]["coaching"]
            assert lift * sign > 0
            # Everyone here is 27: most of the way to a veteran's share.
            level = 4 if sign > 0 else 0
            assert lift == pytest.approx(hp.coaching_lift(level, 27), abs=1e-3)
            goal = before[p.id]["target"] + lift
            assert after["target"] == pytest.approx(max(-1, min(1, goal)), abs=1e-3)


def test_a_player_happy_again_takes_back_his_trade_request(lg):
    pid = lg.players[lg.a.id][0].id
    with (
        patch.object(hp, "target", return_value=-1.0),
        patch.object(hp, "asks_for_trade", side_effect=lambda m, w, t, r: True),
    ):
        _repo(lg).update(lg.season.id, date(2025, 4, 11))
    assert pid in _repo(lg).trade_requests([pid])
    with patch.object(hp, "target", return_value=0.9):
        _repo(lg).update(lg.season.id, date(2025, 4, 18))
        # One better week isn't enough.
        assert pid in _repo(lg).trade_requests([pid])
        for week in range(2, 10):
            _repo(lg).update(lg.season.id, date(2025, 4, 11) + timedelta(weeks=week))
    assert pid not in _repo(lg).trade_requests([pid])
    assert _repo(lg).mood(pid, lg.season.id)["content_weeks"] == 0
    feed = NewsRepository(lg.db).feed(lg.league.id)
    assert any("happy to stay" in s["headline"] for s in feed)


def _middling(personality_for=hp.personality_for):
    """Personalities with middling traits, so a calm player's slow-moving
    mood (low temper) doesn't change how many weeks a test needs."""
    return lambda pid: replace(
        personality_for(pid),
        traits={"ego": 50, "temper": 50, "loyalty": 50},
        ruiner=False,
    )


def test_restless_is_settled_enough_to_take_back_a_request(lg):
    pid = lg.players[lg.a.id][0].id
    with (
        patch.object(hp, "personality_for", _middling()),
        patch.object(hp, "target", return_value=-1.0),
        patch.object(hp, "asks_for_trade", side_effect=lambda m, w, t, r: True),
    ):
        _repo(lg).update(lg.season.id, date(2025, 4, 11))
    # Restless, even with the ignored-request penalty on top.
    with patch.object(hp, "target", return_value=-0.2):
        for week in range(1, 12):
            _repo(lg).update(lg.season.id, date(2025, 4, 11) + timedelta(weeks=week))
    assert hp.mood_word(_repo(lg).mood(pid, lg.season.id)["mood"]) == "restless"
    assert pid not in _repo(lg).trade_requests([pid])
