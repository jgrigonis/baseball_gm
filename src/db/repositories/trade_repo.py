# src/db/repositories/trade_repo.py
import uuid

from src.league.trades.draft_picks import Pick, is_pick, label, parse

# An offer still waiting on someone: the other GM's answer, or the league's
# vote.
OPEN = ("pending", "pending_vote")

_OFFER_SELECT = """SELECT o.*, ft.city || ' ' || ft.mascot AS from_name,
                          tt.city || ' ' || tt.mascot AS to_name
                   FROM trade_offers o
                   JOIN teams ft ON ft.id = o.from_team_id
                   JOIN teams tt ON tt.id = o.to_team_id"""


class TradeRepository:
    """Trade offers, the players in them, the league's votes on them, and the
    league's trade history."""

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
        parent_id: str | None = None,
        expires_period: int | None = None,
        expires_on: str | None = None,
        from_ai: bool = False,
    ) -> str:
        """Store a pending offer. items are (asset id, from_team_id) pairs: a
        player's id, or a draft pick's (src/league/trades/draft_picks.py)."""
        offer_id = str(uuid.uuid4())
        self.conn.execute(
            """INSERT INTO trade_offers
                   (id, league_id, season_id, from_team_id, to_team_id,
                    from_gm_id, created_on, parent_id, expires_period,
                    expires_on, from_ai)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                offer_id,
                league_id,
                season_id,
                from_team_id,
                to_team_id,
                from_gm_id,
                created_on,
                parent_id,
                expires_period,
                expires_on,
                from_ai,
            ),
        )
        for asset_id, side in items:
            pick = parse(asset_id)
            if pick:
                self.conn.execute(
                    """INSERT INTO trade_offer_picks
                           (offer_id, draft_year, round, original_team_id, from_team_id)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (
                        offer_id,
                        pick.draft_year,
                        pick.round,
                        pick.original_team_id,
                        side,
                    ),
                )
            else:
                self.conn.execute(
                    """INSERT INTO trade_offer_items (offer_id, player_id, from_team_id)
                       VALUES (%s, %s, %s)""",
                    (offer_id, asset_id, side),
                )
        return offer_id

    def decide(self, offer_id: str, status: str, reason: str | None) -> None:
        self.conn.execute(
            """UPDATE trade_offers SET status = %s, reason = %s, decided_at = NOW()
               WHERE id = %s""",
            (status, reason, offer_id),
        )

    def get(self, offer_id: str) -> dict | None:
        """One offer with its players (see _with_items)."""
        rows = self._with_items(
            self.conn.execute(
                f"{_OFFER_SELECT} WHERE o.id = %s", (offer_id,)
            ).fetchall()
        )
        return rows[0] if rows else None

    def open_offers(self, league_id: str) -> list[dict]:
        """Every offer still waiting on an answer or a vote, oldest first."""
        return self._with_items(
            self.conn.execute(
                f"""{_OFFER_SELECT}
                    WHERE o.league_id = %s AND o.status = ANY(%s)
                    ORDER BY o.created_at""",
                (league_id, list(OPEN)),
            ).fetchall()
        )

    def offers_to_team(self, league_id: str, team_id: str) -> list[dict]:
        """Offers waiting on this team's answer, oldest first."""
        return self._with_items(
            self.conn.execute(
                f"""{_OFFER_SELECT}
                    WHERE o.league_id = %s AND o.to_team_id = %s
                      AND o.status = 'pending'
                    ORDER BY o.created_at""",
                (league_id, team_id),
            ).fetchall()
        )

    def count_pending_from(self, league_id: str, team_id: str, to_team_id=None) -> int:
        """A team's offers still waiting on the other GM, to anyone or to one
        team."""
        return self.conn.execute(
            """SELECT COUNT(*) AS n FROM trade_offers
               WHERE league_id = %s AND from_team_id = %s AND status = 'pending'
                 AND (%s::text IS NULL OR to_team_id = %s)""",
            (league_id, team_id, to_team_id, to_team_id),
        ).fetchone()["n"]

    def open_to_teams(self, league_id: str, team_ids) -> set[str]:
        """Ids of pending offers to any of these teams (single player: the
        GM's)."""
        rows = self.conn.execute(
            """SELECT id FROM trade_offers
               WHERE league_id = %s AND to_team_id = ANY(%s) AND status = 'pending'""",
            (league_id, list(team_ids)),
        ).fetchall()
        return {r["id"] for r in rows}

    def open_offers_with_players(
        self, league_id: str, asset_ids: list[str]
    ) -> list[str]:
        """Ids of the open offers naming any of these players or picks."""
        player_ids = [a for a in asset_ids if not is_pick(a)]
        picks = [parse(a) for a in asset_ids if is_pick(a)]
        rows = self.conn.execute(
            """SELECT DISTINCT o.id FROM trade_offers o
               JOIN trade_offer_items i ON i.offer_id = o.id
               WHERE o.league_id = %s AND o.status = ANY(%s)
                 AND i.player_id = ANY(%s)""",
            (league_id, list(OPEN), player_ids),
        ).fetchall()
        ids = {r["id"] for r in rows}
        for pick in picks:
            rows = self.conn.execute(
                """SELECT o.id FROM trade_offers o
                   JOIN trade_offer_picks k ON k.offer_id = o.id
                   WHERE o.league_id = %s AND o.status = ANY(%s)
                     AND k.draft_year = %s AND k.round = %s
                     AND k.original_team_id = %s""",
                (
                    league_id,
                    list(OPEN),
                    pick.draft_year,
                    pick.round,
                    pick.original_team_id,
                ),
            ).fetchall()
            ids.update(r["id"] for r in rows)
        return sorted(ids)

    def open_offers_for_team(self, league_id: str, team_id: str) -> list[str]:
        """Ids of the open offers a team is on either side of."""
        rows = self.conn.execute(
            """SELECT id FROM trade_offers
               WHERE league_id = %s AND status = ANY(%s)
                 AND (from_team_id = %s OR to_team_id = %s)""",
            (league_id, list(OPEN), team_id, team_id),
        ).fetchall()
        return [r["id"] for r in rows]

    # ── Offers AI teams make ─────────────────────────────────────────────

    def open_ai_offers_to(self, league_id: str, team_id: str) -> int:
        return self.conn.execute(
            """SELECT COUNT(*) AS n FROM trade_offers
               WHERE league_id = %s AND to_team_id = %s AND from_ai
                 AND status = 'pending'""",
            (league_id, team_id),
        ).fetchone()["n"]

    def ai_offers_to_this_season(self, season_id: str, team_id: str) -> int:
        return self.conn.execute(
            """SELECT COUNT(*) AS n FROM trade_offers
               WHERE season_id = %s AND to_team_id = %s AND from_ai""",
            (season_id, team_id),
        ).fetchone()["n"]

    def last_ai_offer_to(self, season_id: str, team_id: str) -> str | None:
        """The league date of the latest AI offer to this team this season."""
        return self.conn.execute(
            """SELECT MAX(created_on) AS d FROM trade_offers
               WHERE season_id = %s AND to_team_id = %s AND from_ai""",
            (season_id, team_id),
        ).fetchone()["d"]

    def ai_offers_made(
        self, season_id: str, from_team_id: str, to_team_id: str
    ) -> set[frozenset[str]]:
        """The AI offers one team has made another this season, each as the
        set of players in it."""
        rows = self.conn.execute(
            """SELECT o.id, i.player_id FROM trade_offers o
               JOIN trade_offer_items i ON i.offer_id = o.id
               WHERE o.season_id = %s AND o.from_team_id = %s
                 AND o.to_team_id = %s AND o.from_ai""",
            (season_id, from_team_id, to_team_id),
        ).fetchall()
        offers: dict[str, set[str]] = {}
        for r in rows:
            offers.setdefault(r["id"], set()).add(r["player_id"])
        return {frozenset(p) for p in offers.values()}

    def ai_trades_this_season(self, season_id: str) -> dict[str, int]:
        """Trades between two AI teams this season: how many each team was
        in, and the league's total under "all"."""
        rows = self.conn.execute(
            """SELECT o.from_team_id, o.to_team_id FROM trade_offers o
               WHERE o.season_id = %s AND o.from_ai AND o.status = 'accepted'
                 AND NOT EXISTS (
                     SELECT 1 FROM gms g
                     WHERE g.team_id = o.to_team_id AND g.league_id = o.league_id
                       AND NOT g.is_ai)""",
            (season_id,),
        ).fetchall()
        counts = {"all": len(rows)}
        for r in rows:
            for t in (r["from_team_id"], r["to_team_id"]):
                counts[t] = counts.get(t, 0) + 1
        return counts

    def pending_due_on(self, league_id: str, on: str) -> list[str]:
        """Pending offers whose last day (expires_on) has been played."""
        rows = self.conn.execute(
            """SELECT id FROM trade_offers
               WHERE league_id = %s AND status = 'pending'
                 AND expires_on IS NOT NULL AND expires_on <= %s""",
            (league_id, on),
        ).fetchall()
        return [r["id"] for r in rows]

    # ── The league's vote ────────────────────────────────────────────────

    def open_vote(self, offer_id: str, voter_ids: list[str], vote_period) -> None:
        self.conn.execute(
            """UPDATE trade_offers SET status = 'pending_vote', vote_period = %s
               WHERE id = %s""",
            (vote_period, offer_id),
        )
        for gm_id in voter_ids:
            self.conn.execute(
                "INSERT INTO trade_votes (offer_id, gm_id) VALUES (%s, %s)",
                (offer_id, gm_id),
            )

    def cast_vote(self, offer_id: str, gm_id: str, yes: bool) -> bool:
        """Record a GM's vote. False if they aren't a voter on this trade."""
        row = self.conn.execute(
            """UPDATE trade_votes SET vote = %s, voted_at = NOW()
               WHERE offer_id = %s AND gm_id = %s RETURNING gm_id""",
            (yes, offer_id, gm_id),
        ).fetchone()
        return row is not None

    def drop_voter(self, gm_id: str) -> list[str]:
        """Take a GM off every open vote (they left the league). Returns the
        offers whose vote changed."""
        rows = self.conn.execute(
            """DELETE FROM trade_votes v USING trade_offers o
               WHERE v.offer_id = o.id AND v.gm_id = %s
                 AND o.status = 'pending_vote'
               RETURNING v.offer_id""",
            (gm_id,),
        ).fetchall()
        return [r["offer_id"] for r in rows]

    def tally(self, offer_id: str) -> dict:
        """{voters, yes, no}: no counts only votes cast."""
        row = self.conn.execute(
            """SELECT COUNT(*) AS voters,
                      COUNT(*) FILTER (WHERE vote) AS yes,
                      COUNT(*) FILTER (WHERE vote = FALSE) AS no
               FROM trade_votes WHERE offer_id = %s""",
            (offer_id,),
        ).fetchone()
        return dict(row)

    def votes_for_gm(self, league_id: str, gm_id: str) -> list[dict]:
        """Trades this GM can vote on, with their vote so far (None if not
        yet) and the tally."""
        offers = self._with_items(
            self.conn.execute(
                f"""{_OFFER_SELECT}
                    JOIN trade_votes v ON v.offer_id = o.id AND v.gm_id = %s
                    WHERE o.league_id = %s AND o.status = 'pending_vote'
                    ORDER BY o.created_at""",
                (gm_id, league_id),
            ).fetchall()
        )
        for o in offers:
            o["my_vote"] = self.conn.execute(
                "SELECT vote FROM trade_votes WHERE offer_id = %s AND gm_id = %s",
                (o["id"], gm_id),
            ).fetchone()["vote"]
            o["tally"] = self.tally(o["id"])
        return offers

    def waiting_voters(self, offer_id: str) -> list[str]:
        """The voters on a trade who haven't voted."""
        rows = self.conn.execute(
            "SELECT gm_id FROM trade_votes WHERE offer_id = %s AND vote IS NULL",
            (offer_id,),
        ).fetchall()
        return [r["gm_id"] for r in rows]

    def unvoted_count(self, league_id: str, gm_id: str) -> int:
        return self.conn.execute(
            """SELECT COUNT(*) AS n FROM trade_votes v
               JOIN trade_offers o ON o.id = v.offer_id
               WHERE o.league_id = %s AND v.gm_id = %s
                 AND o.status = 'pending_vote' AND v.vote IS NULL""",
            (league_id, gm_id),
        ).fetchone()["n"]

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
                f"""{_OFFER_SELECT}
                   WHERE o.league_id = %s AND o.status = 'accepted'
                   ORDER BY o.created_on DESC, o.decided_at DESC
                   LIMIT %s""",
                (league_id, limit),
            ).fetchall()
        )

    def offers_for_team(
        self, league_id: str, team_id: str, limit: int = 20
    ) -> list[dict]:
        """A team's offers, newest first, whatever their answer: the ones it
        made, and the ones made to it that it has answered (the ones still
        waiting on it are offers_to_team). One waiting on the league's vote
        carries its tally."""
        offers = self._with_items(
            self.conn.execute(
                f"""{_OFFER_SELECT}
                   WHERE o.league_id = %s
                     AND (o.from_team_id = %s
                          OR (o.to_team_id = %s AND o.status <> 'pending'))
                   ORDER BY o.created_at DESC
                   LIMIT %s""",
                (league_id, team_id, team_id, limit),
            ).fetchall()
        )
        for o in offers:
            if o["status"] == "pending_vote":
                o["tally"] = self.tally(o["id"])
        return offers

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
        # Picks read like players: player_id is the pick's id, last_name its
        # label.
        picks = self.conn.execute(
            """SELECT k.*, t.city || ' ' || t.mascot AS team_name
               FROM trade_offer_picks k
               JOIN teams t ON t.id = k.original_team_id
               WHERE k.offer_id = ANY(%s)
               ORDER BY k.draft_year, k.round, team_name""",
            ([o["id"] for o in offers],),
        ).fetchall()
        for k in picks:
            pick = Pick(k["draft_year"], k["round"], k["original_team_id"])
            by_offer.setdefault(k["offer_id"], []).append(
                {
                    "offer_id": k["offer_id"],
                    "from_team_id": k["from_team_id"],
                    "player_id": pick.id,
                    "first_name": "",
                    "last_name": label(pick, k["team_name"]),
                    "position": "",
                    "is_pick": True,
                }
            )
        for o in offers:
            items = by_offer.get(o["id"], [])
            o["sent"] = [i for i in items if i["from_team_id"] == o["from_team_id"]]
            o["received"] = [i for i in items if i["from_team_id"] == o["to_team_id"]]
        return offers
