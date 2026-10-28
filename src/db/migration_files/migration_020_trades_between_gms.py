"""
Trades between human GMs.

An offer to a team another person runs waits for that GM's answer: accept,
reject or counter (a new offer linked by parent_id). It expires at the end of
the period after the one it was made in (expires_period), or at the trade
deadline. In leagues with trade_vote on, an accepted trade goes to a vote of
the league's other GMs (trade_votes) and waits as pending_vote until
vote_period (see src/api/services/trades.py).

stop_for_trade_offers: a single-player league's sims stop when a trade offer
arrives. Trade news reaches GMs as gm_notifications kind 'trade'.
"""

VERSION = 20


def upgrade(conn):
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS "
        "trade_vote BOOLEAN NOT NULL DEFAULT TRUE"
    )
    conn.execute(
        "ALTER TABLE leagues ADD COLUMN IF NOT EXISTS "
        "stop_for_trade_offers BOOLEAN NOT NULL DEFAULT TRUE"
    )
    conn.execute(
        "ALTER TABLE trade_offers ADD COLUMN IF NOT EXISTS "
        "parent_id TEXT REFERENCES trade_offers(id) ON DELETE SET NULL"
    )
    conn.execute(
        "ALTER TABLE trade_offers ADD COLUMN IF NOT EXISTS expires_period INTEGER"
    )
    conn.execute(
        "ALTER TABLE trade_offers ADD COLUMN IF NOT EXISTS vote_period INTEGER"
    )
    conn.execute(
        "ALTER TABLE trade_offers DROP CONSTRAINT IF EXISTS trade_offers_status_check"
    )
    conn.execute(
        """ALTER TABLE trade_offers ADD CONSTRAINT trade_offers_status_check
           CHECK (status IN (
               'pending', 'pending_vote', 'accepted', 'rejected', 'countered',
               'withdrawn', 'expired', 'void', 'voted_down'
           ))"""
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_offers_parent ON trade_offers(parent_id)"
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trade_votes (
            offer_id  TEXT NOT NULL REFERENCES trade_offers(id) ON DELETE CASCADE,
            gm_id     TEXT NOT NULL REFERENCES gms(id)          ON DELETE CASCADE,
            vote      BOOLEAN,
            voted_at  TIMESTAMPTZ,
            PRIMARY KEY (offer_id, gm_id)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_votes_gm ON trade_votes(gm_id)")
    conn.execute(
        "ALTER TABLE gm_notifications DROP CONSTRAINT IF EXISTS gm_notifications_kind_check"
    )
    conn.execute(
        """ALTER TABLE gm_notifications ADD CONSTRAINT gm_notifications_kind_check
           CHECK (kind IN ('injury', 'returned', 'roster', 'trade'))"""
    )
