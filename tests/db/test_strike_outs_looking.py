# tests/db/test_strike_outs_looking.py
import uuid

from src.db.migration_files import migration_014_strike_outs_looking as migration
from src.db.repositories.player_games import PlayerGameRepository
from src.league.offseason.build_season_stats import build_season
from src.stats.stats import Stats


def _struck_out(looking, swinging):
    s = Stats()
    for _ in range(looking):
        s.batting.strike_out(looking=True)
        s.pitching.strike_out(looking=True)
    for _ in range(swinging):
        s.batting.strike_out()
        s.pitching.strike_out()
    return s


def test_strike_outs_looking_saved_and_rolled_up(db_conn, factory):
    season = factory.season()
    home, away = factory.team(), factory.team()
    player = factory.player_row()
    repo = PlayerGameRepository(db_conn)
    for date, looking, swinging in (("2025-04-01", 1, 2), ("2025-04-02", 2, 0)):
        game_id = str(uuid.uuid4())
        db_conn.execute(
            "INSERT INTO games (id, game_date, season_id, home_team_id, away_team_id)"
            " VALUES (%s, %s, %s, %s, %s)",
            (game_id, date, season.id, home.id, away.id),
        )
        repo.insert_player_game(
            game_id, player.id, home.id, away.id, _struck_out(looking, swinging)
        )

    loaded = repo.get_for_game(game_id, player.id)
    assert loaded.batting.strike_outs_looking == 2
    assert loaded.pitching.strike_outs_looking == 2

    totals = repo.get_player_stats_totals(player.id, season.id)
    assert totals["bat_strike_outs"] == 5
    assert totals["bat_strike_outs_looking"] == 3
    assert totals["pitch_strike_outs_looking"] == 3

    build_season(db_conn, season.id)
    row = db_conn.execute(
        """SELECT bat_strike_outs, bat_strike_outs_looking, pitch_strike_outs_looking
           FROM player_season_stats WHERE player_id = %s AND season_id = %s""",
        (player.id, season.id),
    ).fetchone()
    assert dict(row) == {
        "bat_strike_outs": 5,
        "bat_strike_outs_looking": 3,
        "pitch_strike_outs_looking": 3,
    }


def test_migration_is_idempotent(db_conn):
    migration.upgrade(db_conn)
    migration.upgrade(db_conn)
