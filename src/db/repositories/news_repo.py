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
        gm_id: str | None = None,
        hidden: bool = False,
        skip_kinds: list[str] | tuple[str, ...] = (),
    ) -> list[dict]:
        """Stories newest first: by league date, the biggest first on a day,
        then the order written. With `gm_id`, the stories that GM hid with
        the x are left out, or with `hidden` they're the only ones shown;
        `skip_kinds` leaves out whole kinds (the News tab's filter)."""
        where = ["league_id = %s", "weight >= %s"]
        args: list = [league_id, min_weight]
        if gm_id:
            where.append(
                ("" if hidden else "NOT ") + "EXISTS (SELECT 1 FROM news_hidden h"
                " WHERE h.gm_id = %s AND h.news_id = league_news.id)"
            )
            args.append(gm_id)
        if skip_kinds:
            where.append("NOT (kind = ANY(%s))")
            args.append(list(skip_kinds))
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
            f"""SELECT id, season_id, news_date, kind, key, headline, body,
                       weight, team_ids, player_ids, gm_ids
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
        don't count, so the badge is for news worth a look. Nor do the kinds
        they filtered out."""
        row = self.conn.execute(
            """SELECT COUNT(*) AS n FROM league_news n, gms g
               WHERE g.id = %s AND n.league_id = %s AND n.weight >= 2
                 AND n.id > COALESCE(g.news_seen_id, 0)
                 AND NOT (n.kind = ANY(g.news_hidden_kinds))""",
            (gm_id, league_id),
        ).fetchone()
        return row["n"] if row else 0

    def mark_seen(self, gm_id: str, newest_id: int | None) -> None:
        if newest_id is None:
            return
        self.conn.execute(
            """UPDATE gms SET news_seen_id = GREATEST(COALESCE(news_seen_id, 0), %s)
               WHERE id = %s""",
            (newest_id, gm_id),
        )

    # ── Hidden stories and the kind filter (migration 134) ─────────────────

    def set_hidden(self, gm_id: str, news_id: int, hidden: bool) -> None:
        if hidden:
            self.conn.execute(
                """INSERT INTO news_hidden (gm_id, news_id) VALUES (%s, %s)
                   ON CONFLICT DO NOTHING""",
                (gm_id, news_id),
            )
        else:
            self.conn.execute(
                "DELETE FROM news_hidden WHERE gm_id = %s AND news_id = %s",
                (gm_id, news_id),
            )

    def hidden_count(self, league_id: str, gm_id: str, season_id: str | None) -> int:
        row = self.conn.execute(
            """SELECT COUNT(*) AS n FROM news_hidden h
               JOIN league_news n ON n.id = h.news_id
               WHERE h.gm_id = %s AND n.league_id = %s
                 AND (%s::text IS NULL OR n.season_id = %s)""",
            (gm_id, league_id, season_id, season_id),
        ).fetchone()
        return row["n"]

    def story_league(self, news_id: int) -> str | None:
        row = self.conn.execute(
            "SELECT league_id FROM league_news WHERE id = %s", (news_id,)
        ).fetchone()
        return row["league_id"] if row else None

    def hidden_kinds(self, gm_id: str) -> list[str]:
        row = self.conn.execute(
            "SELECT news_hidden_kinds FROM gms WHERE id = %s", (gm_id,)
        ).fetchone()
        return list(row["news_hidden_kinds"] or []) if row else []

    def set_hidden_kinds(self, gm_id: str, kinds: list[str]) -> None:
        self.conn.execute(
            "UPDATE gms SET news_hidden_kinds = %s WHERE id = %s",
            (sorted(set(kinds)), gm_id),
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
