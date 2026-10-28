# src/db/repositories/lineup_preference_repo.py
#
# A person's saved batting orders: one for games against right-handed starters
# (vs_hand R) and one against left-handers (L). A team with only one saved
# uses it against both.

HANDS = ("R", "L")


class LineupPreferenceRepository:
    def __init__(self, conn):
        self.conn = conn

    def save_preferences(self, gm_id: str, lineup: list[dict], vs_hand: str = "R"):
        self.conn.execute(
            "DELETE FROM gm_lineup_preferences WHERE gm_id = %s AND vs_hand = %s",
            (gm_id, vs_hand),
        )
        for slot in lineup:
            self.conn.execute(
                """INSERT INTO gm_lineup_preferences
                   (gm_id, player_id, batting_order, position, is_starter, vs_hand,
                    updated_at)
                   VALUES (%s, %s, %s, %s, TRUE, %s, NOW())""",
                (
                    gm_id,
                    slot["player_id"],
                    slot["batting_order"],
                    slot.get("position"),
                    vs_hand,
                ),
            )

    def get_by_gm_id(self, gm_id: str) -> dict[str, list[dict]]:
        """A GM's saved batting orders (batting_order slots only), ordered, by
        hand: {"R": [...], "L": [...]}. A hand with nothing saved is []."""
        rows = self.conn.execute(
            """SELECT player_id, batting_order, position, vs_hand
               FROM gm_lineup_preferences
               WHERE gm_id = %s AND batting_order IS NOT NULL
               ORDER BY batting_order""",
            (gm_id,),
        ).fetchall()
        by_hand: dict[str, list[dict]] = {h: [] for h in HANDS}
        for r in rows:
            r = dict(r)
            by_hand[r.pop("vs_hand")].append(r)
        return by_hand

    def get_preferences(
        self, team_id: str, league_id: str, vs_hand: str | None = None
    ) -> list[dict] | None:
        """The person's saved lineup against a starter with this hand, or
        their other one if they've saved only one. None for an AI team."""
        gm = self.conn.execute(
            "SELECT id FROM gms WHERE team_id = %s AND league_id = %s AND NOT is_ai LIMIT 1",
            (team_id, league_id),
        ).fetchone()
        if not gm:
            return None
        rows = self.conn.execute(
            """SELECT player_id, batting_order, position, vs_hand
               FROM gm_lineup_preferences WHERE gm_id = %s
               ORDER BY batting_order""",
            (gm["id"],),
        ).fetchall()
        by_hand: dict[str, list[dict]] = {}
        for r in rows:
            r = dict(r)
            by_hand.setdefault(r.pop("vs_hand"), []).append(r)
        if vs_hand in by_hand:
            return by_hand[vs_hand]
        for hand in HANDS:
            if hand in by_hand:
                return by_hand[hand]
        return None
