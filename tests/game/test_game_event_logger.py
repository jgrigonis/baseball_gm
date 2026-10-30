# tests/game/test_game_event_logger.py
"""
GameEventLogger runs inside play_game's transaction, so a failed event insert
must not commit or roll back the rest of the game's writes.
"""

from src.game.game_event_logger import GameEventLogger


def test_failed_insert_keeps_earlier_writes(db_conn, factory):
    team = factory.team()

    # 'middle' violates the half CHECK constraint, so the insert fails.
    GameEventLogger(db_conn, game_id="game-1")._insert(
        team.id, "pitcher_start", inning=1, half="middle"
    )

    row = db_conn.execute("SELECT id FROM teams WHERE id = %s", (team.id,))
    assert row.fetchone() is not None


def test_insert_joins_the_callers_transaction(db_conn, factory):
    game = factory.game_with_teams()

    GameEventLogger(db_conn, game_id=game.id)._insert(
        game.home.id, "pitcher_start", inning=1, half="top"
    )

    row = db_conn.execute(
        "SELECT count(*) AS n FROM game_events WHERE game_id = %s", (game.id,)
    ).fetchone()
    assert row["n"] == 1


def test_closer_label_names_a_save_only_in_a_save_situation():
    from src.game.game_event_logger import closer_entry_label

    assert closer_entry_label(2, save_situation=True) == "in for save (up 2)"
    assert closer_entry_label(0, save_situation=False) == (
        "in, tie game (high leverage)"
    )
    assert closer_entry_label(1, save_situation=False) == ("in, high leverage (up 1)")
