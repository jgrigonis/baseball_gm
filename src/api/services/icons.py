"""Franchise icons: the long-tenured, high-value players a club's owner
wants kept.

A player is an icon of a team when he has played ICON_SEASONS or more
big-league seasons for it (backstory seasons count, and so does the
current one once he's played in it) and is still a good player now: an
overall grade of ICON_MIN_GRADE or better. A star who once made the
All-Star team for us but is washed up now isn't one; neither is a star we
just traded for.

Owners who care about icons (the "icons" weight in src/league/owners.py)
react when one is traded away and mark down the season for each one
traded or released (src/api/services/owner_review.py). Roster, Lineup,
the player panel and the trade builder show the ICON tag so GMs can see
it coming.
"""

from __future__ import annotations

from src.api.grade_curves import GRADES

# Big-league seasons played for the club.
ICON_SEASONS = 5
# The lowest overall grade (on the pro curve) that still counts as high-value.
ICON_MIN_GRADE = "B+"
_GOOD_GRADES = set(GRADES[: GRADES.index(ICON_MIN_GRADE) + 1])


def seasons_with(conn, pairs: list[tuple[str, str]]) -> dict[tuple[str, str], int]:
    """How many regular seasons each (player, team) pair played together."""
    if not pairs:
        return {}
    pids = list({p for p, _ in pairs})
    tids = list({t for _, t in pairs})
    rows = conn.execute(
        """SELECT player_id, team_id, COUNT(DISTINCT season_id) AS n
           FROM player_season_stats
           WHERE player_id = ANY(%s) AND team_id = ANY(%s)
             AND NOT is_postseason
             AND (bat_games_played > 0 OR pitch_games_played > 0)
           GROUP BY player_id, team_id""",
        (pids, tids),
    ).fetchall()
    return {(r["player_id"], r["team_id"]): int(r["n"]) for r in rows}


def _grades(conn, player_ids: list[str]) -> dict[str, str]:
    """Each player's overall grade, as his roster row shows it."""
    from src.api.view_models.player_cards import roster_card

    if not player_ids:
        return {}
    rows = conn.execute(
        """SELECT p.*, ps.status, sk.*
           FROM players p
           JOIN player_status ps ON ps.player_id = p.id
           JOIN player_skills sk ON sk.player_id = p.id
           WHERE p.id = ANY(%s)""",
        (player_ids,),
    ).fetchall()
    out = {}
    for r in rows:
        d = dict(r)
        if d["status"] in ("prospect", "unassigned"):
            d["status"] = "40man"  # graded as a pro, like everyone he'd face
        out[d["id"]] = roster_card(d).get("overall", "?")
    return out


def is_icon_grade(grade: str | None) -> bool:
    return grade in _GOOD_GRADES


def find(
    conn, pairs: list[tuple[str, str]], grades: dict[str, str] | None = None
) -> dict[tuple[str, str], int]:
    """The (player, team) pairs where he's that team's icon, with his
    seasons there. `grades` ({player_id: overall grade}) skips the lookup
    when the caller already has them."""
    tenure = seasons_with(conn, pairs)
    long = [k for k in pairs if tenure.get(k, 0) >= ICON_SEASONS]
    if not long:
        return {}
    if grades is None:
        grades = _grades(conn, list({p for p, _ in long}))
    return {k: tenure[k] for k in long if is_icon_grade(grades.get(k[0]))}


def attach(conn, team_id: str | None, players: list[dict]) -> None:
    """Mark roster/lineup cards of the team's icons: p["icon_seasons"].
    Cards already carry their overall grade."""
    if not team_id:
        return
    pairs = [(p["player_id"], team_id) for p in players if p.get("player_id")]
    grades = {p["player_id"]: p.get("overall") for p in players if p.get("player_id")}
    found = find(conn, pairs, grades)
    for p in players:
        n = found.get((p.get("player_id"), team_id))
        if n:
            p["icon_seasons"] = n
