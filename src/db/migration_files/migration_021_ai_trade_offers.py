"""
AI-initiated trade offers.

from_ai: an AI team made the offer. expires_on: an offer an AI team makes to
the GM of a single-player league expires after this league date (multiplayer
offers use expires_period). See src/api/services/ai_trades.py.
"""

VERSION = 21


def upgrade(conn):
    conn.execute("ALTER TABLE trade_offers ADD COLUMN IF NOT EXISTS expires_on TEXT")
    conn.execute(
        "ALTER TABLE trade_offers ADD COLUMN IF NOT EXISTS "
        "from_ai BOOLEAN NOT NULL DEFAULT FALSE"
    )
