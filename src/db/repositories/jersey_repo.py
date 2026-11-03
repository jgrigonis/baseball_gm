# src/db/repositories/jersey_repo.py
"""
Jersey numbers on team rosters (rules in src/player/jersey_numbers.py).

Uses tables:
- players.jersey_prefs        the numbers a player wants, favorite first
- team_players.jersey_number  the number he wears on that team
"""

from __future__ import annotations

import random

from src.player import jersey_numbers as jn


class JerseyRepository:
    def __init__(self, conn):
        self.conn = conn

    def prefs(self, player_id: str) -> list[str]:
        row = self.conn.execute(
            "SELECT jersey_prefs FROM players WHERE id = %s", (player_id,)
        ).fetchone()
        return jn.clean_prefs(row["jersey_prefs"] if row else None, player_id)

    def numbers_on_team(self, team_id: str) -> dict[str, str]:
        """number -> player_id for everyone wearing one on the team."""
        rows = self.conn.execute(
            """
            SELECT player_id, jersey_number FROM team_players
            WHERE team_id = %s AND jersey_number IS NOT NULL
            """,
            (team_id,),
        ).fetchall()
        return {r["jersey_number"]: r["player_id"] for r in rows}

    def number_of(self, team_id: str, player_id: str) -> str | None:
        row = self.conn.execute(
            """
            SELECT jersey_number FROM team_players
            WHERE team_id = %s AND player_id = %s
            """,
            (team_id, player_id),
        ).fetchone()
        return row["jersey_number"] if row else None

    def _set(self, team_id: str, player_id: str, number: str | None) -> None:
        self.conn.execute(
            """
            UPDATE team_players SET jersey_number = %s
            WHERE team_id = %s AND player_id = %s
            """,
            (number, team_id, player_id),
        )

    def assign(self, team_id: str, player_id: str) -> str | None:
        """
        Give a player who just joined the team his number, if he doesn't
        have one there yet. Returns the number (None if he isn't on the team).
        """
        row = self.conn.execute(
            """
            SELECT jersey_number FROM team_players
            WHERE team_id = %s AND player_id = %s
            """,
            (team_id, player_id),
        ).fetchone()
        if row is None:
            return None
        if row["jersey_number"] is not None:
            return row["jersey_number"]

        rng = random.Random(f"jersey:{team_id}:{player_id}")
        prefs = self.prefs(player_id)
        holders = self.numbers_on_team(team_id)
        star = _StarCheck(self.conn, team_id, player_id)

        number, bumped = jn.choose_number(
            prefs,
            holders,
            rng,
            will_defer=lambda holder: star.veteran_defers(holder, rng),
        )
        if bumped is not None:
            # The veteran picks again from his own list (nobody bumps him).
            taken = set(holders) | {number}
            self._set(team_id, bumped, jn.open_number(self.prefs(bumped), taken, rng))
        self._set(team_id, player_id, number)
        return number

    def backfill_team(self, team_id: str) -> None:
        """Numbers for everyone on the team without one, most senior first
        (most seasons with the team, then oldest). Nobody is bumped."""
        rows = self.conn.execute(
            """
            SELECT tp.player_id, p.jersey_prefs
            FROM team_players tp
            JOIN players p ON p.id = tp.player_id
            LEFT JOIN player_skills sk ON sk.player_id = tp.player_id
            LEFT JOIN LATERAL (
                SELECT COUNT(DISTINCT pss.season_id) AS seasons
                FROM player_season_stats pss
                WHERE pss.player_id = tp.player_id AND pss.team_id = tp.team_id
                  AND NOT pss.is_postseason
            ) s ON TRUE
            WHERE tp.team_id = %s AND tp.jersey_number IS NULL
            ORDER BY COALESCE(s.seasons, 0) DESC, sk.age DESC NULLS LAST, tp.player_id
            """,
            (team_id,),
        ).fetchall()
        if not rows:
            return
        taken = set(self.numbers_on_team(team_id))
        rng = random.Random(f"jersey-backfill:{team_id}")
        for r in rows:
            n = jn.open_number(
                jn.clean_prefs(r["jersey_prefs"], r["player_id"]), taken, rng
            )
            taken.add(n)
            self._set(team_id, r["player_id"], n)


class _StarCheck:
    """Rates the team only if a held number makes it matter."""

    def __init__(self, conn, team_id: str, newcomer_id: str):
        self.conn = conn
        self.team_id = team_id
        self.newcomer_id = newcomer_id
        self._ratings: dict[str, int] | None = None
        self._ages: dict[str, int] = {}

    def _load(self) -> dict[str, int]:
        if self._ratings is None:
            # Imported here: player_repo -> ... -> team_repo -> this module.
            from src.db.repositories.player_repo import PlayerRepository
            from src.player.player_value import role_rating

            players = PlayerRepository(self.conn).get_players_by_team(self.team_id)
            self._ratings = {p.id: role_rating(p) for p in players}
            self._ages = {p.id: p.age for p in players}
        return self._ratings

    def veteran_defers(self, holder_id: str, rng: random.Random) -> bool:
        ratings = self._load()
        mine = ratings.get(self.newcomer_id)
        if mine is None or holder_id not in ratings:
            return False
        rank = 1 + sum(
            1 for pid, r in ratings.items() if pid != self.newcomer_id and r > mine
        )
        return jn.defers(
            holder_age=self._ages[holder_id],
            holder_rating=ratings[holder_id],
            newcomer_rating=mine,
            newcomer_team_rank=rank,
            rng=rng,
        )
