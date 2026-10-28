# src/db/migration_files/migration_019_trades.py
"""
Trades.

trade_offers holds every offer one team makes another, with its answer, and
trade_offer_items the players in it. Accepted offers are the league's trade
history (see src/api/services/trades.py).

Also lets a GM's news say the game moved a player to keep their roster
between 25 and 40 (gm_notifications kind 'roster').
"""

VERSION = 19


def upgrade(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_offers (
            id           TEXT PRIMARY KEY,
            league_id    TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
            season_id    TEXT NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
            from_team_id TEXT NOT NULL REFERENCES teams(id)   ON DELETE CASCADE,
            to_team_id   TEXT NOT NULL REFERENCES teams(id)   ON DELETE CASCADE,
            from_gm_id   TEXT REFERENCES gms(id) ON DELETE SET NULL,
            status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
                             'pending', 'accepted', 'rejected', 'countered',
                             'withdrawn', 'expired', 'void'
                         )),
            reason       TEXT,
            created_on   TEXT NOT NULL,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            decided_at   TIMESTAMPTZ
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_offer_items (
            offer_id     TEXT NOT NULL REFERENCES trade_offers(id) ON DELETE CASCADE,
            player_id    TEXT NOT NULL REFERENCES players(id)      ON DELETE CASCADE,
            from_team_id TEXT NOT NULL REFERENCES teams(id)        ON DELETE CASCADE,
            PRIMARY KEY (offer_id, player_id)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_offers_league "
        "ON trade_offers(league_id, season_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_offer_items_player "
        "ON trade_offer_items(player_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_offers_season    ON trade_offers(season_id);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_offers_from_team ON trade_offers(from_team_id);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_offers_to_team   ON trade_offers(to_team_id);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_offers_from_gm   ON trade_offers(from_gm_id);"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_offer_items_team ON trade_offer_items(from_team_id);"
    )
    conn.execute(
        "ALTER TABLE gm_notifications DROP CONSTRAINT IF EXISTS gm_notifications_kind_check"
    )
    conn.execute(
        """ALTER TABLE gm_notifications ADD CONSTRAINT gm_notifications_kind_check
           CHECK (kind IN ('injury', 'returned', 'roster'))"""
    )
