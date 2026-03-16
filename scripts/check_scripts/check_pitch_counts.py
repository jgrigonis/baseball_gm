import sqlite3
from pathlib import Path

db_path = Path("leagues/league.db")  # Adjust path as needed
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

cursor = conn.execute(
    """
SELECT 
    p.first_name || ' ' || p.last_name as pitcher,
    COUNT(*) as starts,
    AVG(pgs.pitch_count) as avg_pitches,
    MAX(pgs.pitch_count) as max_pitches,
    MIN(pgs.pitch_count) as min_pitches
FROM player_game_stats pgs
JOIN players p ON p.id = pgs.player_id
WHERE pgs.pitch_game_started = 1
GROUP BY pgs.player_id
ORDER BY avg_pitches DESC;
"""
)
rows = cursor.fetchall()
for row in rows:
    print(
        f"{row['pitcher']}: {row['starts']} starts, {row['avg_pitches']:.1f} avg, {row['max_pitches']} max, {row['min_pitches']} min"
    )
