# src/db/repositories/talent_cap_repo.py
"""
TalentCapRepository

Stores and retrieves per-player talent caps. Caps are written once at
player creation and never updated — they represent immutable talent
ceilings determined at birth.
"""

from collections.abc import Sequence
from src.player.positions import SKILLS

_SKILLS = list(SKILLS.keys())


class TalentCapRepository:
    """Read and write talent caps for players."""

    def __init__(self, conn) -> None:
        self.conn = conn

    # ─────────────────────────────────────────────
    #  Write
    # ─────────────────────────────────────────────

    def insert_talent_caps(self, player_id: str, caps: dict[str, int]) -> None:
        """
        Insert talent caps for a newly created player.

        Should only be called once per player. Silently ignores duplicate
        inserts (INSERT) so re-running generation is safe.

        Args:
            player_id: Player UUID
            caps:      Dict mapping skill name → cap value
        """
        cols = ", ".join(_SKILLS)
        placeholders = ", ".join("%s" for _ in _SKILLS)
        values = tuple(caps.get(sk, 50) for sk in _SKILLS)

        self.conn.execute(
            f"""
            INSERT INTO player_talent_caps
                (player_id, {cols})
            VALUES
                (%s, {placeholders})
            ON CONFLICT DO NOTHING
            """,
            (player_id, *values),
        )
        # self.conn.commit()

    # Only called in tests
    def insert_many_talent_caps(
        self, records: Sequence[tuple[str, dict[str, int]]]
    ) -> None:
        """
        Bulk insert caps for multiple players.

        Args:
            records: List of (player_id, caps_dict) tuples
        """
        cols = ", ".join(_SKILLS)
        placeholders = ", ".join("%s" for _ in _SKILLS)

        rows = [
            (player_id, *tuple(caps.get(sk, 50) for sk in _SKILLS))
            for player_id, caps in records
        ]

        self.conn.cursor().executemany(
            f"""
            INSERT INTO player_talent_caps
                (player_id, {cols})
            VALUES
                (%s, {placeholders})
            ON CONFLICT DO NOTHING
            """,
            rows,
        )
        # self.conn.commit()

    # ─────────────────────────────────────────────
    #  Read
    # ─────────────────────────────────────────────

    def get(self, player_id: str) -> dict[str, int] | None:
        """
        Retrieve talent caps for a single player.

        Args:
            player_id: Player UUID

        Returns:
            Dict mapping skill name → cap, or None if not found.
            Missing caps default to 100 (uncapped) so older players
            without caps in the DB still age correctly.
        """
        row = self.conn.execute(
            "SELECT * FROM player_talent_caps WHERE player_id = %s",
            (player_id,),
        ).fetchone()

        if row is None:
            return None

        return {sk: row[sk] for sk in _SKILLS}

    def get_many(self, player_ids: Sequence[str]) -> dict[str, dict[str, int]]:
        """
        Retrieve talent caps for multiple players in one query.

        Args:
            player_ids: List of player UUIDs

        Returns:
            Dict mapping player_id → caps dict.
            Players not found are omitted from the result.
        """
        if not player_ids:
            return {}

        result = {}
        chunk_size = 900

        for i in range(0, len(player_ids), chunk_size):
            chunk = player_ids[i : i + chunk_size]
            placeholders = ",".join("%s" for _ in chunk)
            rows = self.conn.execute(
                f"SELECT * FROM player_talent_caps WHERE player_id IN ({placeholders})",
                chunk,
            ).fetchall()
            for row in rows:
                result[row["player_id"]] = {sk: row[sk] for sk in _SKILLS}

        return result

    def exists(self, player_id: str) -> bool:
        """Check whether caps exist for a player."""
        row = self.conn.execute(
            "SELECT 1 FROM player_talent_caps WHERE player_id = %s",
            (player_id,),
        ).fetchone()
        return row is not None
