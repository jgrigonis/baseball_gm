# src/db/repositories/news_repo.py
"""The league news feed's stories (league_news) and how far the feed has got
in each season (league_seasons.news_through / news_closed)."""

from __future__ import annotations


class NewsRepository:
    def __init__(self, conn):
        self.conn = conn

    # ── Stories ──────────────────────────────────────────────────────────────

    def add(
        self,
        league_id: str,
        season_id: str | None,
        news_date: str,
        kind: str,
        key: str,
        headline: str,
        body: str = "",
        weight: int = 1,
        team_ids: list[str] | None = None,
        player_ids: list[str] | None = None,
        gm_ids: list[str] | None = None,
    ) -> bool:
        """Write a story unless the league already has one with this key.
        Returns whether it was written."""
        row = self.conn.execute(
            """INSERT INTO league_news (league_id, season_id, news_date, kind, key,
                   headline, body, weight, team_ids, player_ids, gm_ids)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (league_id, key) DO NOTHING
               RETURNING id""",
            (
                league_id, season_id, news_date, kind, key, headline, body,
                max(1, min(3, weight)),
                [t for t in (team_ids or []) if t],
                [p for p in (player_ids or []) if p],
                [g for g in (gm_ids or []) if g],
            ),
        ).fetchone()  # fmt: skip
        return row is not None

    def has(self, league_id: str, key: str) -> bool:
        return (
            self.conn.execute(
                "SELECT 1 FROM league_news WHERE league_id = %s AND key = %s",
                (league_id, key),
            ).fetchone()
            is not None
        )

    def feed(
        self,
        league_id: str,
        season_id: str | None = None,
        team_id: str | None = None,
        min_weight: int = 1,
        limit: int = 60,
        before_id: int | None = None,
    ) -> list[dict]:
        """Stories newest first: by league date, the biggest first on a day,
        then the order written."""
        where = ["league_id = %s", "weight >= %s"]
        args: list = [league_id, min_weight]
        if season_id:
            where.append("season_id = %s")
            args.append(season_id)
        if team_id:
            where.append("%s = ANY(team_ids)")
            args.append(team_id)
        if before_id:
            # Older than that story in the feed's order.
            where.append(
                "(news_date, weight, id) <"
                " (SELECT news_date, weight, id FROM league_news WHERE id = %s)"
            )
            args.append(before_id)
        args.append(limit)
        rows = self.conn.execute(
            f"""SELECT id, season_id, news_date, kind, headline, body, weight,
                       team_ids, player_ids, gm_ids
                FROM league_news WHERE {" AND ".join(where)}
                ORDER BY news_date DESC, weight DESC, id DESC LIMIT %s""",
            args,
        ).fetchall()
        return [dict(r) for r in rows]

    def seasons(self, league_id: str) -> list[dict]:
        """The seasons with stories, newest first ({id, year})."""
        rows = self.conn.execute(
            """SELECT DISTINCT s.id, s.year FROM league_news n
               JOIN seasons s ON s.id = n.season_id
               WHERE n.league_id = %s ORDER BY s.year DESC""",
            (league_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def newest_id(self, league_id: str) -> int | None:
        row = self.conn.execute(
            "SELECT MAX(id) AS id FROM league_news WHERE league_id = %s",
            (league_id,),
        ).fetchone()
        return row["id"] if row else None

    def count_unseen(self, league_id: str, gm_id: str) -> int:
        """Stories since the GM last opened the News tab. Notes (weight 1)
        don't count, so the badge is for news worth a look."""
        row = self.conn.execute(
            """SELECT COUNT(*) AS n FROM league_news n
               WHERE n.league_id = %s AND n.weight >= 2
                 AND n.id > COALESCE((SELECT news_seen_id FROM gms WHERE id = %s), 0)""",
            (league_id, gm_id),
        ).fetchone()
        return row["n"]

    def mark_seen(self, gm_id: str, newest_id: int | None) -> None:
        if newest_id is None:
            return
        self.conn.execute(
            """UPDATE gms SET news_seen_id = GREATEST(COALESCE(news_seen_id, 0), %s)
               WHERE id = %s""",
            (newest_id, gm_id),
        )

    # ── Progress ─────────────────────────────────────────────────────────────

    def progress(self, league_id: str) -> dict[str, dict]:
        """season_id -> {news_through, news_closed} for the league's seasons."""
        rows = self.conn.execute(
            """SELECT season_id, news_through, news_closed FROM league_seasons
               WHERE league_id = %s""",
            (league_id,),
        ).fetchall()
        return {r["season_id"]: dict(r) for r in rows}

    def set_through(self, league_id: str, season_id: str, through: str | None) -> None:
        self.conn.execute(
            """UPDATE league_seasons SET news_through = %s
               WHERE league_id = %s AND season_id = %s""",
            (through, league_id, season_id),
        )

    def close(self, league_id: str, season_id: str) -> None:
        self.conn.execute(
            """UPDATE league_seasons SET news_closed = TRUE
               WHERE league_id = %s AND season_id = %s""",
            (league_id, season_id),
        )

    def started(self, league_id: str) -> bool:
        """Whether the feed has caught up with the league before."""
        row = self.conn.execute(
            """SELECT 1 FROM league_seasons
               WHERE league_id = %s AND (news_through IS NOT NULL OR news_closed)
               LIMIT 1""",
            (league_id,),
        ).fetchone()
        return row is not None
