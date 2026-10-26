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
