# tests/api/web/test_schedule_links.py
"""Each upcoming opponent on the schedule links to that team's roster and
stats, the same as the team names in the standings."""

import uuid

from fastapi.testclient import TestClient

from src.api.database import get_db
from src.api.dependencies import get_current_gm, get_current_user
from src.api.main import app


def test_upcoming_opponents_link_to_their_stats(db_conn, factory):
    league = factory.league(state="season")
    season = factory.season(year=2025)
    factory.league_season(league, season)
    mine = factory.team(city="My", mascot="Team")
    opp = factory.team(city="Chicago", mascot="Wind")
    for team in (mine, opp):
        factory.league_season_team(league, season, team)
    gm = factory.gm(team=mine, league=league, is_ai=False)
    db_conn.execute(
        """INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id,
               completed)
           VALUES (%s, '2025-04-01', %s, %s, %s, 0)""",
        (str(uuid.uuid4()), season.id, mine.id, opp.id),
    )

    app.dependency_overrides[get_db] = lambda: db_conn
    app.dependency_overrides[get_current_user] = lambda: {"id": None}
    app.dependency_overrides[get_current_gm] = lambda: {
        "id": gm.id,
        "team_id": mine.id,
    }
    try:
        html = TestClient(app).get(f"/leagues/{league.id}/schedule").text
    finally:
        app.dependency_overrides.clear()

    upcoming = html.split("Upcoming")[1].split("Recent Results")[0]
    assert f"/leagues/{league.id}/stats?team_id={opp.id}" in upcoming
    # Both the opponent and the top bar's own team carry their color badge
    assert ">CHI</span>Chicago Wind" in upcoming
    topbar = html.split('class="topbar-team"')[1].split("</a>")[0]
    assert ">MY</span>" in topbar
    # and links back to the Meet your team page
    assert topbar.startswith(f' href="/leagues/{league.id}/welcome"')
