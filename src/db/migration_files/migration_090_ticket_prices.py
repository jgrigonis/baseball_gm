# src/db/migration_files/migration_090_ticket_prices.py
"""
Ticket prices (Josh, 2026-11-07): the GM sets them on a 1 to 10 slider
between seasons (src/league/finances.py TICKET_*). team_budgets gets a
ticket_price column; NULL is the default, 5. The revenue column stays the
revenue before ticket prices, so the league's fixed costs don't move.
"""

VERSION = 90


def upgrade(conn):
    conn.execute(
        "ALTER TABLE team_budgets ADD COLUMN IF NOT EXISTS ticket_price SMALLINT"
    )
