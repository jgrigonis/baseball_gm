# scripts/league_leaders.py
"""
Display the stat leaders for various stats for a season, compar with expected 
real-world ranges.

Usage:
    python league_leaders.py --db leagues/league.db --id <season_id>
    python league_leaders.py --db leagues/league.db  # auto-selects if one season
"""

import argparse
import sqlite3
from pathlib import Path

# TODO
