VERSION = 1


def upgrade(conn):
    """
    Add detailed pitching columns to player_game_stats.
    Safe to run multiple times.
    """
    existing = _get_columns(conn, "player_game_stats")

    columns = {
        "pitch_doubles": "INTEGER DEFAULT 0",
        "pitch_triples": "INTEGER DEFAULT 0",
        "pitch_pickoffs": "INTEGER DEFAULT 0",
        "pitch_balks": "INTEGER DEFAULT 0",
        "pitch_wild_pitches": "INTEGER DEFAULT 0",
    }

    for col, ddl in columns.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE player_game_stats ADD COLUMN {col} {ddl}")


def _get_columns(conn, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()

    return {row[1] for row in rows}
