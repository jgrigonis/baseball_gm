# src/api/services/records/feats.py
"""
record_feats: the single games and streaks good enough for a top five,
the league's or a club's (defs.py says which, and why they're kept).

Keeper decides what's worth keeping while a batch of games is read, with
the cut-offs it loaded at the start; they only ever rise, so a stale one
just keeps a little more.
"""

from __future__ import annotations

from collections import defaultdict

from src.api.services.records.core import LIST_SIZE

COLS = (
    "league_id", "kind", "stat", "key", "value", "subject", "player_id",
    "team_id", "season_id", "year", "game_id", "on_date", "start_date",
    "opp_team_id", "innings", "source", "active",
)  # fmt: skip


def _cut(values: list[int]) -> int:
    """The value it takes to make a top five (ties count)."""
    if len(values) < LIST_SIZE:
        return 0
    return sorted(values, reverse=True)[LIST_SIZE - 1]


class Keeper:
    """The current top values for one kind of feat, league-wide and per club."""

    def __init__(self, conn, league_id: str, kind: str):
        self.conn = conn
        self.league_id = league_id
        self.kind = kind
        self.league: dict[str, list[int]] = defaultdict(list)
        self.club: dict[tuple[str, str], list[int]] = defaultdict(list)
        self.best: dict[str, int] = {}
        rows = conn.execute(
            """SELECT stat, team_id, value FROM record_feats
               WHERE league_id = %s AND kind = %s""",
            (league_id, kind),
        ).fetchall()
        for r in rows:
            self._note(r["stat"], r["team_id"], r["value"])

    def _note(self, stat: str, team_id: str | None, value: int) -> None:
        self.league[stat].append(value)
        if team_id:
            self.club[(stat, team_id)].append(value)
        if value > self.best.get(stat, 0):
            self.best[stat] = value

    def worth(self, stat: str, team_id: str | None, value: int, keep: int) -> bool:
        if value < keep:
            return False
        return value >= min(
            _cut(self.league[stat]),
            _cut(self.club[(stat, team_id)]) if team_id else 10**9,
        )

    def add(self, stat: str, team_id: str | None, value: int) -> None:
        self._note(stat, team_id, value)
        # Keep the lists short: only what can still matter for a cut-off.
        for lst in (self.league[stat], self.club[(stat, team_id)] if team_id else []):
            if len(lst) > 40:
                lst.sort(reverse=True)
                del lst[20:]


def save(conn, rows: list[dict]) -> None:
    """Write feats; a streak already saved (same key) is brought up to date."""
    if not rows:
        return
    cols = ", ".join(COLS)
    marks = ", ".join(["%s"] * len(COLS))
    with conn.cursor() as cur:
        cur.executemany(
            f"""INSERT INTO record_feats ({cols}) VALUES ({marks})
                ON CONFLICT (league_id, key) DO UPDATE SET
                    value = EXCLUDED.value, on_date = EXCLUDED.on_date,
                    active = EXCLUDED.active, team_id = EXCLUDED.team_id""",
            [tuple(r.get(c) for c in COLS) for r in rows],
        )


def load(conn, league_id: str, kind: str, team_id: str | None = None) -> list[dict]:
    rows = conn.execute(
        """SELECT f.*, p.first_name, p.last_name, t.city, t.mascot,
                  o.city AS opp_city
           FROM record_feats f
           LEFT JOIN players p ON p.id = f.player_id
           LEFT JOIN teams t ON t.id = f.team_id
           LEFT JOIN teams o ON o.id = f.opp_team_id
           WHERE f.league_id = %s AND f.kind = %s
             AND (%s::text IS NULL OR f.team_id = %s)""",
        (league_id, kind, team_id, team_id),
    ).fetchall()
    return [dict(r) for r in rows]
