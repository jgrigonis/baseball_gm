"""
Platoon Usage defaults to vs Handedness: a regular sits against a same-side
starter only for a bench player who's close to him. People's teams still on
None (the old default) move to it, and AI teams take their persona's setting
again (src/league/personas.py), which is now vs Handedness for most.
"""

VERSION = 27


def upgrade(conn):
    from src.league import personas

    conn.execute(
        "ALTER TABLE gm_profiles ALTER COLUMN platoon_usage SET DEFAULT 'vs-handedness'"
    )
    conn.execute(
        """
        UPDATE gm_profiles gp SET platoon_usage = 'vs-handedness'
        FROM gms g
        WHERE g.id = gp.gm_id AND NOT g.is_ai AND gp.platoon_usage = 'none'
        """
    )
    rows = conn.execute(
        """
        SELECT g.id, p.dials FROM gms g
        JOIN gm_personas p ON p.id = g.persona_id
        WHERE g.is_ai
        """
    ).fetchall()
    for r in rows:
        conn.execute(
            "UPDATE gm_profiles SET platoon_usage = %s WHERE gm_id = %s",
            (personas.profile(r["dials"])["platoon_usage"], r["id"]),
        )
