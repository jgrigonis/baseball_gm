"""
Contract prices follow how a player ranks in his league, not his raw rating
(Josh, 2026-11-09). Ratings climb over a league's seasons, and prices pinned
to fixed grade cutoffs climbed with them (a sim's cap went $155M to $328M in
six seasons). Each season the league's price level is stored the first time
a deal for it is priced: the rating at the top PRICE_LINE of big leaguers, by
kind (src/player/contracts.py price_level). Deals are priced on a rating
moved by how far that level has risen since the league's first season.
"""

VERSION = 110


def upgrade(conn):
    conn.execute(
        """CREATE TABLE IF NOT EXISTS league_price_levels (
               league_id TEXT NOT NULL REFERENCES leagues(id) ON DELETE CASCADE,
               year INTEGER NOT NULL,
               kind TEXT NOT NULL,
               level REAL NOT NULL,
               PRIMARY KEY (league_id, year, kind)
           )"""
    )
