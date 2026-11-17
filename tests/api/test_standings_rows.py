# tests/api/test_standings_rows.py
"""The standings table (src/api/view_models/standings.py): streaks and L10."""

import uuid

from src.api.view_models.standings import standings_rows
from tests.api.test_trades import lg  # noqa: F401


def _game(db, season, home, away, date, home_won=True, series_id=None):
    gid = str(uuid.uuid4())
    winner = home if home_won else away
    db.execute(
        """INSERT INTO games (id, game_date, season_id, series_id, home_team_id,
               away_team_id, home_score, away_score, winner_id, completed, innings_played)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, 9)""",
        (gid, date, season.id, series_id, home.id, away.id,
         5 if home_won else 3, 3 if home_won else 5, winner.id),
    )  # fmt: skip
    for team, won in ((home, home_won), (away, not home_won)):
        db.execute(
            "INSERT INTO team_game_stats (game_id, team_id, runs, win, loss)"
            " VALUES (%s, %s, 4, %s, %s)",
            (gid, team.id, int(won), int(not won)),
        )


def _row(rows, team):
    return next(r for r in rows if r["team_id"] == team.id)


def test_a_streak_runs_past_ten(lg):  # noqa: F811
    db = lg.db
    db.execute("DELETE FROM games WHERE season_id = %s", (lg.season.id,))
    _game(db, lg.season, lg.mine, lg.theirs, "2025-04-01", home_won=False)
    for day in range(2, 15):  # 13 straight
        _game(db, lg.season, lg.mine, lg.theirs, f"2025-04-{day:02d}")
    rows = standings_rows(db, lg.league.id, lg.season.id, lg.mine.id)
    assert _row(rows, lg.mine)["streak"] == "W13"
    assert _row(rows, lg.theirs)["streak"] == "L13"
    assert _row(rows, lg.mine)["l10"] == "10-0"
