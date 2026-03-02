# scripts/league_leaders.py
"""
Display the stat leaders for various stats for a season, compar with expected
real-world ranges.

Usage:
    python league_leaders.py --db leagues/league.db --id <season_id>
    python league_leaders.py --db leagues/league.db  # auto-selects if one season

Stat leader categories to compare to expected:
Batting:
- Home Runs
- Triples
- Doubles
- Singles
- Hits
- RBI
- Sac Flies
- Sac Bunts
- Stolen Bases
- Caught Stealing
(SB% already in league_totals)
- Walks (batting)
- Strikeouts (batting)
- lowest K/AB
or (depending on available data)
- highest AB/K
- batting averages
- OBP
- Slugging
- OPS
- wOBA
- wRC

Pitching:
- Innings Pitched
- Game Starts
- ERA
- Wins
- Losses
- Saves
- Save Opps
- SV / SVO
- WHIP
- K/9
- BB/9
- Balks
- Wild Pitches

Fielding (By positions):
- Putouts
- Assists
- Errors
- FPCT
"""

import argparse
import sqlite3
from pathlib import Path

# TODO
