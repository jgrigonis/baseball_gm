# tests/api/test_playoffs_bracket.py
"""The playoff bracket marks the viewer's team and other human GMs' teams, so
the template can colour them like the standings do."""

from src.api.view_models.playoffs import playoffs_context


def _series(db, season, name, home, away):
    sid = f"{season.id}-{name}"
    db.execute(
        "INSERT INTO series (id, season_id, name) VALUES (%s, %s, %s)",
        (sid, season.id, name),
    )
    db.execute(
        """INSERT INTO games
        (id, game_date, season_id, series_id, home_team_id, away_team_id, completed)
        VALUES (%s, '2025-10-01', %s, %s, %s, %s, 0)""",
        (f"{sid}-g1", season.id, sid, home.id, away.id),
    )


def test_bracket_flags_mine_and_other_humans(db_conn, factory):
    league = factory.league(state="playoffs")
    season = factory.season()
    factory.league_season(league, season)
    mine, rival, ai, ai2 = (factory.team() for _ in range(4))
    factory.gm(team=mine, league=league, is_ai=False)
    factory.gm(team=rival, league=league, is_ai=False)
    factory.gm(team=ai, league=league, is_ai=True)
    _series(db_conn, season, "1v8", mine, rival)
    _series(db_conn, season, "4v5", ai, ai2)

    ctx = playoffs_context(db_conn, league.id, season.id, mine.id)

    teams = {t["team_id"]: t for s in ctx["bracket"][0]["series"] for t in s["teams"]}
    assert teams[mine.id]["is_mine"] and not teams[mine.id]["is_human"]
    assert teams[rival.id]["is_human"] and not teams[rival.id]["is_mine"]
    assert not teams[ai.id]["is_human"]
    assert not teams[ai2.id]["is_human"]


def _win(db, season, name, winner, loser, wins):
    sid = f"{season.id}-{name}"
    db.execute(
        "INSERT INTO series (id, season_id, name) VALUES (%s, %s, %s)",
        (sid, season.id, name),
    )
    for i in range(wins):
        db.execute(
            """INSERT INTO games
            (id, game_date, season_id, series_id, home_team_id, away_team_id,
             completed, winner_id)
            VALUES (%s, '2025-10-01', %s, %s, %s, %s, 1, %s)""",
            (f"{sid}-g{i}", season.id, sid, winner.id, loser.id, winner.id),
        )


def test_finals_show_a_semifinal_winner_before_games_exist(db_conn, factory):
    league = factory.league(state="playoffs")
    season = factory.season()
    factory.league_season(league, season)
    a, b = factory.team(), factory.team()
    _win(db_conn, season, "[1,8]v[4,5]", a, b, 4)
    db_conn.execute(
        "INSERT INTO series (id, season_id, name) VALUES (%s, %s, 'Finals')",
        (f"{season.id}-Finals", season.id),
    )

    ctx = playoffs_context(db_conn, league.id, season.id, a.id)

    finals = ctx["bracket"][2]["series"][0]
    assert [t["team_id"] for t in finals["teams"]] == [a.id]
    assert finals["teams"][0]["pending"]


def _game(db, sid, season, n, date, home, away, winner):
    db.execute(
        """INSERT INTO games
        (id, game_date, season_id, series_id, home_team_id, away_team_id,
         completed, winner_id)
        VALUES (%s, %s, %s, %s, %s, %s, 1, %s)""",
        (f"{sid}-g{n}", date, season.id, sid, home.id, away.id, winner.id),
    )


def test_bracket_marks_the_latest_playoff_day(db_conn, factory):
    """The last day's games show larger and the day before shrinks back;
    series that played that day get a top-to-bottom order, and one won that
    day is marked clinched."""
    league = factory.league(state="playoffs")
    season = factory.season()
    factory.league_season(league, season)
    a, b, c, d = (factory.team() for _ in range(4))
    sids = {}
    for name in ("1v8", "4v5"):
        sids[name] = f"{season.id}-{name}"
        db_conn.execute(
            "INSERT INTO series (id, season_id, name) VALUES (%s, %s, %s)",
            (sids[name], season.id, name),
        )
    # 1v8: a sweeps on Oct 1-3, clinching on the latest day.
    for n, day in enumerate(("2025-10-01", "2025-10-02", "2025-10-03")):
        _game(db_conn, sids["1v8"], season, n, day, a, b, a)
    # 4v5: split the first two days, idle on the latest day.
    _game(db_conn, sids["4v5"], season, 0, "2025-10-01", c, d, c)
    _game(db_conn, sids["4v5"], season, 1, "2025-10-02", c, d, d)

    r1 = playoffs_context(db_conn, league.id, season.id, a.id)["bracket"][0]
    s18, s45 = r1["series"][0], r1["series"][1]
    assert [g["latest"] for g in s18["completed_games"]] == [False, False, True]
    assert [g["prev"] for g in s18["completed_games"]] == [False, True, False]
    assert s18["clinched_today"] and s18["latest_order"] == 0
    assert not any(g["latest"] for g in s45["completed_games"])
    assert s45["latest_order"] is None and not s45["clinched_today"]
