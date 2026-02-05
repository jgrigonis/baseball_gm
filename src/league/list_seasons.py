# src/league/list_seasons.py

from pathlib import Path
import sqlite3

from src.db.repositories.season_repo import SeasonRepository
from src.util.locations import LEAGUE_FILES_DIR


db = "league.db"
conn = sqlite3.connect(Path(LEAGUE_FILES_DIR) / db)
conn.row_factory = sqlite3.Row

sr = SeasonRepository(conn)

for season in sr.get_all_seasons():
    print(season)
