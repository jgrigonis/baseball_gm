import sqlite3

from src.db.connection import get_connection


conn = get_connection()
cur = conn.cursor()

cur.execute("DELETE FROM pitcher_state")
conn.commit()
conn.close()
print("Success!")
