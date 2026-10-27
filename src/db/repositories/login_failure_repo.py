# src/db/repositories/login_failure_repo.py
#
# Rows of login_failures: one per wrong password at sign-in. Usernames arrive
# here already lowercased, and include names no account has.


class LoginFailureRepository:
    def __init__(self, db):
        self.db = db

    def add(self, username: str, ip: str | None) -> None:
        self.db.execute(
            "INSERT INTO login_failures (username, ip) VALUES (%s, %s)",
            (username, ip),
        )

    def seconds_blocked(
        self, column: str, value: str, limit: int, window_minutes: int
    ) -> float:
        """How long until fewer than `limit` failures for this username or ip
        fall in the last `window_minutes`; 0 if that's already true."""
        assert column in ("username", "ip")
        row = self.db.execute(
            f"""SELECT EXTRACT(EPOCH FROM
                       created_at + make_interval(mins => %s) - NOW()) AS wait
                FROM login_failures
                WHERE {column} = %s
                  AND created_at > NOW() - make_interval(mins => %s)
                ORDER BY created_at DESC
                OFFSET %s LIMIT 1""",
            (window_minutes, value, window_minutes, limit - 1),
        ).fetchone()
        return max(float(row["wait"]), 0.0) if row else 0.0

    def clear(self, username: str) -> None:
        self.db.execute("DELETE FROM login_failures WHERE username = %s", (username,))

    def delete_old(self, days: int = 1) -> None:
        self.db.execute(
            "DELETE FROM login_failures WHERE created_at < NOW() - make_interval(days => %s)",
            (days,),
        )
