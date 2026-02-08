import sqlite3

conn = sqlite3.connect("leagues/league.db")
cursor = conn.cursor()
cursor.execute("DELETE FROM pitcher_state")
conn.commit()
conn.close()
print("Success!")
