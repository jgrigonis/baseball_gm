# scripts/list_seasons.py

from pathlib import Path
import sqlite3

from src.db.repositories.season_repo import SeasonRepository
from src.util.locations import LEAGUE_FILES_DIR
from src.db.connection import get_connection

db = "league.db"
conn = get_connection(db)

sr = SeasonRepository(conn)

for season in sr.get_all_seasons():
    print(season)
