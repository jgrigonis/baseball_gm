"""
Draft pick trades.

leagues.pick_trades: the league lets teams trade draft picks (off unless
the commissioner turns it on at creation). trade_offer_picks: the picks in an
offer, beside its players in trade_offer_items. See
src/league/trades/draft_picks.py.
"""

VERSION = 22


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS "
        "pick_trades BOOLEAN NOT NULL DEFAULT FALSE"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_offer_picks (
            offer_id         TEXT    NOT NULL,
            draft_year       INTEGER NOT NULL,
            round            INTEGER NOT NULL,
            original_team_id TEXT    NOT NULL,
            from_team_id     TEXT    NOT NULL,

            PRIMARY KEY (offer_id, draft_year, round, original_team_id),

            FOREIGN KEY (offer_id)         REFERENCES trade_offers(id) ON DELETE CASCADE,
            FOREIGN KEY (original_team_id) REFERENCES teams(id)        ON DELETE CASCADE,
            FOREIGN KEY (from_team_id)     REFERENCES teams(id)        ON DELETE CASCADE
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_offer_picks_original "
        "ON trade_offer_picks(original_team_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_offer_picks_team "
        "ON trade_offer_picks(from_team_id)"
    )
