# src/league/team_resolver.py
"""
Resolve a team ID from a partial city or mascot name.

Usage (standalone):
    python team_resolver.py --db league.db knights
    python team_resolver.py --db league.db "los angeles"

Usage (as a library):
    from src.db.repositories.team_resolver import resolve_team_id
    team_id = resolve_team_id(conn, "knights")
"""

import argparse
import sqlite3
from pathlib import Path

from src.util.locations import LEAGUE_FILES_DIR


# ---------------------------------------------------------------------------
# Core resolver
# ---------------------------------------------------------------------------


class TeamResolverError(Exception):
    pass


def resolve_team_id(conn, query: str) -> str:
    """
    Resolve a team ID from a partial or full city/mascot name.

    Matching priority:
      1. Exact match on city or mascot (case-insensitive)
      2. Prefix match on city or mascot
      3. Substring match on city or mascot

    Raises TeamResolverError if no match or ambiguous match is found.

    Args:
        conn:  DB connection with row_factory = sqlite3.Row
        query: City name, mascot name, or partial of either

    Returns:
        Team ID string
    """
    q = query.strip().lower()

    rows = conn.execute(
        "SELECT id, city, mascot FROM teams ORDER BY city, mascot"
    ).fetchall()

    def score(row) -> int | None:
        city = row["city"].lower()
        mascot = row["mascot"].lower()
        if city == q or mascot == q:
            return 0  # exact
        if city.startswith(q) or mascot.startswith(q):
            return 1  # prefix
        if q in city or q in mascot:
            return 2  # substring
        return None

    scored = [(score(r), r) for r in rows]
    matches = [(s, r) for s, r in scored if s is not None]

    if not matches:
        all_teams = ", ".join(f"{r['city']} {r['mascot']}" for r in rows)
        raise TeamResolverError(
            f"No team found matching '{query}'.\nAvailable teams: {all_teams}"
        )

    best_score = min(s for s, _ in matches)
    best = [r for s, r in matches if s == best_score]

    if len(best) > 1:
        options = ", ".join(f"{r['city']} {r['mascot']}" for r in best)
        raise TeamResolverError(
            f"Ambiguous team name '{query}' — matched: {options}\n"
            f"Please be more specific."
        )

    return best[0]["id"]


def resolve_team(conn, query: str) -> dict:
    """
    Like resolve_team_id but returns the full team row (id, city, mascot).
    """
    team_id = resolve_team_id(conn, query)
    row = conn.execute(
        "SELECT id, city, mascot FROM teams WHERE id = ?", (team_id,)
    ).fetchone()
    return dict(row)


# ---------------------------------------------------------------------------
# Standalone usage
# ---------------------------------------------------------------------------


def get_args():
    p = argparse.ArgumentParser(
        description="Look up a team ID from a city or mascot name."
    )
    p.add_argument("--db", "-d", default="league.db", help="DB file name")
    p.add_argument("query", help="City or mascot name (partial ok)")
    return p.parse_args()


def main():
    args = get_args()

    conn = sqlite3.connect(Path(LEAGUE_FILES_DIR) / args.db)
    conn.row_factory = sqlite3.Row

    try:
        team = resolve_team(conn, args.query)
        print(f"{team['city']} {team['mascot']}")
        print(f"  ID: {team['id']}")
    except TeamResolverError as e:
        print(f"❌ {e}")


if __name__ == "__main__":
    main()
