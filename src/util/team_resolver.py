# src/util/team_resolver.py
"""
Resolve a team from a flexible user-supplied string.

Accepts any of:
  - UUID:              "3a4b5c..."
  - City only:         "Vienna"
  - Mascot only:       "Maestros"
  - City + Mascot:     "Vienna Maestros"

Matching is case-insensitive. Raises TeamResolverError if no match or ambiguous.
"""

import sqlite3


class TeamResolverError(ValueError):
    pass


def resolve_team(conn: sqlite3.Connection, query: str) -> dict:
    """
    Return a dict with keys: id, city, mascot, name.

    Raises TeamResolverError if no match or ambiguous.
    """
    q = query.strip()

    # 1. Exact UUID
    row = _fetchone(conn, "SELECT id, city, mascot FROM teams WHERE id = ?", (q,))
    if row:
        return row

    # 2. Exact full name  "Vienna Maestros"
    row = _fetchone(
        conn,
        "SELECT id, city, mascot FROM teams WHERE LOWER(city || ' ' || mascot) = LOWER(?)",
        (q,),
    )
    if row:
        return row

    # 3. Exact city
    rows = _fetchall(
        conn, "SELECT id, city, mascot FROM teams WHERE LOWER(city) = LOWER(?)", (q,)
    )
    if len(rows) == 1:
        return rows[0]
    if len(rows) > 1:
        raise TeamResolverError(_ambiguous(q, rows))

    # 4. Exact mascot
    rows = _fetchall(
        conn, "SELECT id, city, mascot FROM teams WHERE LOWER(mascot) = LOWER(?)", (q,)
    )
    if len(rows) == 1:
        return rows[0]
    if len(rows) > 1:
        raise TeamResolverError(_ambiguous(q, rows))

    # 5. Partial match on city or mascot
    rows = _fetchall(
        conn,
        "SELECT id, city, mascot FROM teams"
        " WHERE LOWER(city) LIKE LOWER(?) OR LOWER(mascot) LIKE LOWER(?)",
        (f"%{q}%", f"%{q}%"),
    )
    if len(rows) == 1:
        return rows[0]
    if len(rows) > 1:
        raise TeamResolverError(_ambiguous(q, rows))

    raise TeamResolverError(f"No team found matching '{q}'")


def list_teams(conn: sqlite3.Connection) -> list[dict]:
    """Return all teams sorted by city."""
    return _fetchall(conn, "SELECT id, city, mascot FROM teams ORDER BY city")


# ── Internal helpers ──────────────────────────────────────────────────────────


def _to_dict(row) -> dict:
    if hasattr(row, "keys"):
        return {
            "id": row["id"],
            "city": row["city"],
            "mascot": row["mascot"],
            "name": f"{row['city']} {row['mascot']}",
        }
    return {
        "id": row[0],
        "city": row[1],
        "mascot": row[2],
        "name": f"{row[1]} {row[2]}",
    }


def _fetchone(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return _to_dict(row) if row else None


def _fetchall(conn, sql, params=()):
    return [_to_dict(r) for r in conn.execute(sql, params).fetchall()]


def _ambiguous(query, rows):
    names = ", ".join(r["name"] for r in rows)
    return (
        f"Ambiguous team '{query}' — matches: {names}\n"
        f"Use the full name or UUID to disambiguate."
    )
