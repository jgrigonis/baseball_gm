"""
The Advanced draft board, where a GM ranked the whole prospect pool by hand,
is gone: every team drafts by its draft strategy (need chips, age slider and
pins). Its saved ranked lists go with it.
"""

VERSION = 31


def upgrade(conn):
    conn.execute("DROP TABLE IF EXISTS draft_preferences")
