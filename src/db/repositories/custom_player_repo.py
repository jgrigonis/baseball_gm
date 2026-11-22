"""custom_players rows: a contributor's made-up players
(src/api/services/custom_players.py, migration 151)."""

from __future__ import annotations

import uuid

from psycopg.types.json import Jsonb

_COLS = (
    "id, owner_id, first_name, last_name, position, bats, throws, age, skills,"
    " caps, personality, face, home_region, jersey_prefs, created_at, updated_at"
)
_JSON = ("skills", "caps", "personality", "face")
_FIELDS = (
    "first_name",
    "last_name",
    "position",
    "bats",
    "throws",
    "age",
    "skills",
    "caps",
    "personality",
    "face",
    "home_region",
    "jersey_prefs",
)


def _values(player: dict) -> list:
    return [Jsonb(player[f]) if f in _JSON else player[f] for f in _FIELDS]


class CustomPlayerRepository:
    def __init__(self, db):
        self.db = db

    def list_for(self, owner_id: str) -> list[dict]:
        rows = self.db.execute(
            f"SELECT {_COLS} FROM custom_players WHERE owner_id = %s"
            " ORDER BY updated_at DESC",
            (owner_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get(self, player_id: str) -> dict | None:
        row = self.db.execute(
            f"SELECT {_COLS} FROM custom_players WHERE id = %s", (player_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_many(self, ids) -> dict[str, dict]:
        ids = list(ids)
        if not ids:
            return {}
        rows = self.db.execute(
            f"SELECT {_COLS} FROM custom_players WHERE id = ANY(%s)", (ids,)
        ).fetchall()
        return {r["id"]: dict(r) for r in rows}

    def create(self, owner_id: str, player: dict) -> str:
        player_id = uuid.uuid4().hex
        self.db.execute(
            f"""INSERT INTO custom_players (id, owner_id, {", ".join(_FIELDS)})
                VALUES (%s, %s, {", ".join(["%s"] * len(_FIELDS))})""",
            [player_id, owner_id, *_values(player)],
        )
        return player_id

    def update(self, player_id: str, player: dict) -> None:
        sets = ", ".join(f"{f} = %s" for f in _FIELDS)
        self.db.execute(
            f"UPDATE custom_players SET {sets}, updated_at = NOW() WHERE id = %s",
            [*_values(player), player_id],
        )

    def delete(self, player_id: str) -> None:
        self.db.execute("DELETE FROM custom_players WHERE id = %s", (player_id,))
