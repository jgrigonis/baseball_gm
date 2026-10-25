# src/db/repositories/notification_repo.py
from psycopg.types.json import Jsonb


class NotificationRepository:
    """News for one GM, e.g. injuries on their team during a sim."""

    def __init__(self, conn):
        self.conn = conn

    def add(self, gm_id: str, kind: str, payload: dict) -> None:
        self.conn.execute(
            "INSERT INTO gm_notifications (gm_id, kind, payload) VALUES (%s, %s, %s)",
            (gm_id, kind, Jsonb(payload)),
        )

    def take_unseen(self, gm_id: str) -> list[dict]:
        """Return the GM's unseen news, oldest first, and mark it seen."""
        rows = self.conn.execute(
            """UPDATE gm_notifications SET seen_at = NOW()
               WHERE gm_id = %s AND seen_at IS NULL
               RETURNING id, kind, payload""",
            (gm_id,),
        ).fetchall()
        return [
            {"kind": r["kind"], **r["payload"]}
            for r in sorted(rows, key=lambda r: r["id"])
        ]
