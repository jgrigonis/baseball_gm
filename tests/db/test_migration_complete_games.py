# tests/db/test_migration_complete_games.py
import uuid

from src.db.migration_files import migration_012_complete_games as migration
from src.db.repositories.player_games import PlayerGameRepository
from src.league.offseason.build_season_stats import build_season
from src.stats.stats import Stats


def _pitched(outs, hits, runs, started):
    s = Stats()
    s.pitching.game_played = 1
    s.pitching.game_started = started
    s.pitching.outs = outs
    s.pitching.hits = hits
    s.pitching.runs = runs
    return s


def test_backfills_past_games(db_conn, factory):
    season = factory.season()
    home, away = factory.team(), factory.team()
    ace, starter, reliever = (
        factory.player_row(),
        factory.player_row(),
        factory.player_row(),
    )
    game_id = str(uuid.uuid4())
    db_conn.execute(
        "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)"
        " VALUES (%s, %s, %s, %s, %s)",
        (game_id, "2025-04-01", season.id, home.id, away.id),
    )
    repo = PlayerGameRepository(db_conn)
    # Stats saved before games credited CG/SHO/NH, so all flags are 0
    repo.insert_player_game(game_id, ace.id, home.id, away.id, _pitched(27, 0, 0, 1))
    repo.insert_player_game(
        game_id, starter.id, away.id, home.id, _pitched(21, 4, 2, 1)
    )
    repo.insert_player_game(
        game_id, reliever.id, away.id, home.id, _pitched(3, 0, 0, 0)
    )
    build_season(db_conn, season.id)

    migration.upgrade(db_conn)

    rows = {
        r["player_id"]: r
        for r in db_conn.execute(
            """SELECT player_id, pitch_complete_game, pitch_shutout, pitch_no_hitter
               FROM player_game_stats WHERE game_id = %s""",
            (game_id,),
        ).fetchall()
    }
    assert (
        rows[ace.id]["pitch_complete_game"],
        rows[ace.id]["pitch_shutout"],
        rows[ace.id]["pitch_no_hitter"],
    ) == (1, 1, 1)
    assert rows[starter.id]["pitch_complete_game"] == 0
    assert rows[reliever.id]["pitch_complete_game"] == 0

    season_row = db_conn.execute(
        """SELECT pitch_complete_games, pitch_shutouts, pitch_no_hitters
           FROM player_season_stats WHERE player_id = %s AND season_id = %s""",
        (ace.id, season.id),
    ).fetchone()
    assert dict(season_row) == {
        "pitch_complete_games": 1,
        "pitch_shutouts": 1,
        "pitch_no_hitters": 1,
    }
    assert repo.get_no_hitters(season.id)[0]["player_id"] == ace.id
