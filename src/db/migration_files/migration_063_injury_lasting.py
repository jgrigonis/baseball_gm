"""
Lasting injury effects (plans/injury-details.md, phase 3): when a player
comes back, his injury's outcome is rolled once and written into his skills
(and sometimes his talent caps).

player_injuries.log_id points at the injury's log row; lasting_done is set
once the outcome has been rolled. player_injury_log keeps the outcome, the
points each skill moved (effects), whether the talent caps dropped too, and
the league date and season it happened in.

Injuries already over when this runs are marked done, so nobody's old injury
suddenly changes his ratings. Typed injuries still running get their outcome
when they end.
"""

VERSION = 63


def upgrade(conn):
    conn.execute("ALTER TABLE player_injuries ADD COLUMN IF NOT EXISTS log_id INTEGER")
    conn.execute(
        "ALTER TABLE player_injuries ADD COLUMN IF NOT EXISTS"
        " lasting_done BOOLEAN NOT NULL DEFAULT FALSE"
    )
    for col, typ in (
        ("outcome", "TEXT"),
        ("effects", "JSONB"),
        ("cap_drop", "BOOLEAN"),
        ("resolved_on", "TEXT"),
        ("resolved_season_id", "TEXT"),
    ):
        conn.execute(
            f"ALTER TABLE player_injury_log ADD COLUMN IF NOT EXISTS {col} {typ}"
        )
    # The log row of each running injury: the player's latest of that type.
    conn.execute(
        """UPDATE player_injuries pi SET log_id = (
               SELECT l.id FROM player_injury_log l
               WHERE l.player_id = pi.player_id
                 AND l.injury_type = pi.injury_type
               ORDER BY l.injury_date DESC, l.id DESC LIMIT 1)
           WHERE pi.log_id IS NULL AND pi.injury_type IS NOT NULL"""
    )
    # Done: untyped, unmatched, or already back by the league's current date
    # (the day after its last completed game).
    conn.execute(
        """UPDATE player_injuries pi SET lasting_done = TRUE
           WHERE pi.injury_type IS NULL OR pi.log_id IS NULL
              OR pi.return_date IS NULL
              OR pi.return_date::date <= (
                   SELECT MAX(g.game_date)::date + 1 FROM games g
                   JOIN league_seasons ls ON ls.season_id = g.season_id
                   WHERE ls.league_id = pi.league_id AND g.completed = 1)"""
    )
