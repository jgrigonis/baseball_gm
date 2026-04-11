# scripts/check_scripts/check_all_positions_defensive_stats.py

from src.db.connection import get_connection

conn = get_connection()


POSITIONS = [
    ("c", "Catcher"),
    ("1b", "First Base"),
    ("2b", "Second Base"),
    ("3b", "Third Base"),
    ("ss", "Shortstop"),
    ("lf", "Left Field"),
    ("cf", "Center Field"),
    ("rf", "Right Field"),
    ("p", "Pitcher"),
]

for pos_code, pos_name in POSITIONS:
    cursor = conn.execute(
        """
        SELECT
            p.first_name,
            p.last_name,
            SUM(f.putouts) AS putouts,
            SUM(f.assists) AS assists,
            SUM(f.errors)  AS errors
        FROM players p
        JOIN player_game_fielding f ON p.id = f.player_id
        WHERE f.position = ?
        GROUP BY p.id, p.first_name, p.last_name
        ORDER BY p.last_name, p.first_name;
        """,
        (pos_code,),
    )
    rows = cursor.fetchall()

    print(f"\n{pos_name}")
    print(f"{'Last Name':<15} {'First Name':<15} {'PO':>5} {'A':>5} {'E':>5}")
    print("-" * 45)
    for row in rows:
        print(
            f"{row['last_name']:<15} {row['first_name']:<15} {row['putouts']:>5} {row['assists']:>5} {row['errors']:>5}"
        )
