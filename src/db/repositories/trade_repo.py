# src/db/repositories/trade_repo.py
import uuid


class TradeRepository:
    """Trade offers, the players in them, and the league's trade history."""

    def __init__(self, conn):
        self.conn = conn

    def create_offer(
        self,
        league_id: str,
        season_id: str,
        from_team_id: str,
        to_team_id: str,
        from_gm_id: str | None,
        created_on: str,
        items: list[tuple[str, str]],
    ) -> str:
        """Store a pending offer. items are (player_id, from_team_id) pairs."""
        offer_id = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO trade_offers
                   (id, league_id, season_id, from_team_id, to_team_id,
                    from_gm_id, created_on)
               VALUES (%s, %s, %s, %s, %s, %s, %s)""",
            (
                offer_id,
                league_id,
                season_id,
                from_team_id,
                to_team_id,
                from_gm_id,
                created_on,
            ),
        )
        for player_id, side in items:
            self.conn.execute(
                """INSERT INTO trade_offer_items (offer_id, player_id, from_team_id)
                   VALUES (%s, %s, %s)""",
                (offer_id, player_id, side),
            )
        return offer_id

    def decide(self, offer_id: str, status: str, reason: str | None) -> None:
        self.conn.execute(
            """UPDATE trade_offers SET status = %s, reason = %s, decided_at = NOW()
               WHERE id = %s""",
            (status, reason, offer_id),
        )

    def rejections_today(
        self, league_id: str, from_team_id: str, to_team_id: str, on: str
    ) -> int:
        """How many offers from one team another turned down on a league date."""
        return self.conn.execute(
            """SELECT COUNT(*) AS n FROM trade_offers
               WHERE league_id = %s AND from_team_id = %s AND to_team_id = %s
                 AND created_on = %s AND status = 'rejected'""",
            (league_id, from_team_id, to_team_id, on),
        ).fetchone()["n"]

    def former_teams(self, season_id: str, player_ids: list[str]) -> dict[str, set]:
        """{player_id: teams he was traded away from this season}."""
        if not player_ids:
            return {}
        rows = self.conn.execute(
            """SELECT i.player_id, i.from_team_id
               FROM trade_offer_items i
               JOIN trade_offers o ON o.id = i.offer_id
               WHERE o.season_id = %s AND o.status = 'accepted'
                 AND i.player_id = ANY(%s)""",
            (season_id, player_ids),
        ).fetchall()
        result: dict[str, set] = {}
        for r in rows:
            result.setdefault(r["player_id"], set()).add(r["from_team_id"])
        return result

    def history(self, league_id: str, limit: int = 100) -> list[dict]:
        """Completed trades, newest first. Each has `sent` (the players the
        proposing team gave up) and `received` (the ones it got)."""
        return self._with_items(
            self.conn.execute(
                """SELECT o.*, ft.city || ' ' || ft.mascot AS from_name,
                          tt.city || ' ' || tt.mascot AS to_name
                   FROM trade_offers o
                   JOIN teams ft ON ft.id = o.from_team_id
                   JOIN teams tt ON tt.id = o.to_team_id
                   WHERE o.league_id = %s AND o.status = 'accepted'
                   ORDER BY o.created_on DESC, o.decided_at DESC
                   LIMIT %s""",
                (league_id, limit),
            ).fetchall()
        )

    def offers_from_team(
        self, league_id: str, team_id: str, limit: int = 20
    ) -> list[dict]:
        """A team's own offers, newest first, whatever their answer."""
        return self._with_items(
            self.conn.execute(
                """SELECT o.*, ft.city || ' ' || ft.mascot AS from_name,
                          tt.city || ' ' || tt.mascot AS to_name
                   FROM trade_offers o
                   JOIN teams ft ON ft.id = o.from_team_id
                   JOIN teams tt ON tt.id = o.to_team_id
                   WHERE o.league_id = %s AND o.from_team_id = %s
                   ORDER BY o.created_at DESC
                   LIMIT %s""",
                (league_id, team_id, limit),
            ).fetchall()
        )

    def _with_items(self, offers) -> list[dict]:
        offers = [dict(o) for o in offers]
        if not offers:
            return []
        rows = self.conn.execute(
            """SELECT i.offer_id, i.from_team_id, p.id AS player_id,
                      p.first_name, p.last_name, p.position
               FROM trade_offer_items i
               JOIN players p ON p.id = i.player_id
               WHERE i.offer_id = ANY(%s)
               ORDER BY p.last_name, p.first_name""",
            ([o["id"] for o in offers],),
        ).fetchall()
        by_offer: dict[str, list] = {}
        for r in rows:
            by_offer.setdefault(r["offer_id"], []).append(dict(r))
        for o in offers:
            items = by_offer.get(o["id"], [])
            o["sent"] = [i for i in items if i["from_team_id"] == o["from_team_id"]]
            o["received"] = [i for i in items if i["from_team_id"] == o["to_team_id"]]
        return offers
