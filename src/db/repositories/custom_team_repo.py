# src/db/repositories/custom_team_repo.py
"""custom_teams rows: a contributor's teams of real player-seasons
(src/api/services/custom_teams.py, migration 096)."""

from __future__ import annotations

import uuid

from psycopg.types.json import Jsonb

_COLS = "id, owner_id, name, share_code, copied_from, players, created_at, updated_at"


class CustomTeamRepository:
    def __init__(self, db):
        self.db = db

    def list_for(self, owner_id: str) -> list[dict]:
        rows = self.db.execute(
            f"SELECT {_COLS} FROM custom_teams WHERE owner_id = %s"
            " ORDER BY updated_at DESC",
            (owner_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def get(self, team_id: str) -> dict | None:
        row = self.db.execute(
            f"SELECT {_COLS} FROM custom_teams WHERE id = %s", (team_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_by_code(self, code: str) -> dict | None:
        row = self.db.execute(
            f"SELECT {_COLS} FROM custom_teams WHERE share_code = %s", (code,)
        ).fetchone()
        return dict(row) if row else None

    def code_taken(self, code: str) -> bool:
        return (
            self.db.execute(
                "SELECT 1 FROM custom_teams WHERE share_code = %s", (code,)
            ).fetchone()
            is not None
        )

    def create(
        self,
        owner_id: str,
        name: str,
        share_code: str,
        players: list[dict],
        copied_from: str | None = None,
    ) -> str:
        team_id = uuid.uuid4().hex
        self.db.execute(
            """INSERT INTO custom_teams
                   (id, owner_id, name, share_code, copied_from, players)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (team_id, owner_id, name, share_code, copied_from, Jsonb(players)),
        )
        return team_id

    def save_players(self, team_id: str, players: list[dict]) -> None:
        self.db.execute(
            "UPDATE custom_teams SET players = %s, updated_at = NOW() WHERE id = %s",
            (Jsonb(players), team_id),
        )

    def rename(self, team_id: str, name: str) -> None:
        self.db.execute(
            "UPDATE custom_teams SET name = %s, updated_at = NOW() WHERE id = %s",
            (name, team_id),
        )

    def delete(self, team_id: str) -> None:
        self.db.execute("DELETE FROM custom_teams WHERE id = %s", (team_id,))
