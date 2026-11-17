"""Class grade vs now grade (Josh, 2026-11-17).

The Draft board grades a prospect against his own draft class (the prospect
rating on the prospect curve); every other screen grades players against
pros. So the board marks its letter CLASS and shows the pro "now" grade
beside it, and a drafted player keeps the class grade he had on draft day
(draft_picks.class_grade, migration 141): a dim CLASS tag on his Roster row
through his first season, and a "Drafted ..." line in his player panel.
"""

from __future__ import annotations

from src.api.view_models.player_cards import class_grade
from src.db.repositories.player_repo import PlayerRepository


def record(conn, draft_id: str, player_id: str) -> None:
    """Keep the class grade a pick had when he was taken."""
    row = conn.execute(
        "SELECT throws FROM players WHERE id = %s", (player_id,)
    ).fetchone()
    grade = class_grade(
        PlayerRepository(conn).get_player_skills(player_id),
        row["throws"] if row else None,
    )
    if grade:
        conn.execute(
            """UPDATE draft_picks SET class_grade = %s
               WHERE draft_id = %s AND player_id = %s""",
            (grade, draft_id, player_id),
        )


def attach(conn, league_id: str, season_id: str | None, players: list[dict]) -> None:
    """p["class_grade"] on cards of players taken in this season's draft
    (a draft belongs to the season his first year is), so the tag lasts
    through his first season."""
    if not season_id or not players:
        return
    rows = conn.execute(
        """SELECT dp.player_id, dp.class_grade
           FROM draft_picks dp JOIN drafts d ON d.id = dp.draft_id
           WHERE d.league_id = %s AND d.season_id = %s
             AND dp.class_grade IS NOT NULL
             AND dp.player_id = ANY(%s)""",
        (league_id, season_id, [p["player_id"] for p in players]),
    ).fetchall()
    grades = {r["player_id"]: r["class_grade"] for r in rows}
    for p in players:
        g = grades.get(p["player_id"])
        if g:
            p["class_grade"] = g


def drafted(conn, league_id: str, player_id: str) -> dict | None:
    """His draft pick for the player panel: year, round, pick in the round
    and class grade, or None when he wasn't drafted or it's from before
    class grades were kept."""
    row = conn.execute(
        """SELECT s.year, dp.round, dp.class_grade,
                  dp.pick_number - (SELECT MIN(p2.pick_number) FROM draft_picks p2
                                    WHERE p2.draft_id = dp.draft_id
                                      AND p2.round = dp.round) + 1 AS in_round
           FROM draft_picks dp
           JOIN drafts d ON d.id = dp.draft_id
           JOIN seasons s ON s.id = d.season_id
           WHERE dp.player_id = %s AND d.league_id = %s
             AND dp.class_grade IS NOT NULL
           ORDER BY s.year DESC LIMIT 1""",
        (player_id, league_id),
    ).fetchone()
    return dict(row) if row else None
