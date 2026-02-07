# scripts/check_tables.py
from pathlib import Path
import sqlite3

from src.util.locations import LEAGUE_FILES_DIR

db_path = Path(LEAGUE_FILES_DIR) / "league.db"

print(f"Attempting to open: {db_path}")
print(f"Absolute path: {db_path.absolute()}")
print(f"File exists: {db_path.exists()}")
print(f"File size: {db_path.stat().st_size if db_path.exists() else 'N/A'} bytes")

if not db_path.exists():
    print("\n❌ DATABASE FILE DOES NOT EXIST AT THIS PATH!")
    print("\nPlease check where your actual league.db file is located.")
    print(f"Expected location: {db_path.absolute()}")
else:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()

    print("\nTables in database:")
    if tables:
        for table in tables:
            print(f"  - {table[0]}")
    else:
        print("  (no tables found)")

    conn.close()
