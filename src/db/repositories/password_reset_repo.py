# src/db/repositories/password_reset_repo.py
#
# Rows of password_resets: one per emailed reset link. Tokens arrive here
# already hashed; the plain token only ever exists in the email.


class PasswordResetRepository:
    def __init__(self, db):
        self.db = db

    def find_account(self, login: str) -> dict | None:
        """The account a forgot-password request names, by username or email
        (any case). Only accounts with a login can be reset."""
        row = self.db.execute(
            """SELECT id, username, email FROM users
               WHERE username IS NOT NULL
                 AND (lower(username) = lower(%s) OR lower(email) = lower(%s))""",
            (login, login),
        ).fetchone()
        return dict(row) if row else None

    def recent_count(self, user_id: str, window_minutes: int) -> int:
        return self.db.execute(
            """SELECT COUNT(*) AS n FROM password_resets
               WHERE user_id = %s
                 AND created_at > NOW() - make_interval(mins => %s)""",
            (user_id, window_minutes),
        ).fetchone()["n"]

    def insert(self, user_id: str, token_hash: str, ttl_minutes: int, ip: str | None):
        """A new link. Any earlier link for the account stops working, but
        its row stays so it still counts toward recent_count."""
        self.db.execute(
            """UPDATE password_resets SET expires_at = NOW()
               WHERE user_id = %s AND used_at IS NULL AND expires_at > NOW()""",
            (user_id,),
        )
        self.db.execute(
            """INSERT INTO password_resets (user_id, token_hash, expires_at, requested_ip)
               VALUES (%s, %s, NOW() + make_interval(mins => %s), %s)""",
            (user_id, token_hash, ttl_minutes, ip),
        )

    def find_valid(self, token_hash: str) -> dict | None:
        """The account a link resets, if it's unused and unexpired."""
        row = self.db.execute(
            """SELECT u.id, u.username FROM password_resets r
               JOIN users u ON u.id = r.user_id
               WHERE r.token_hash = %s AND r.used_at IS NULL AND r.expires_at > NOW()""",
            (token_hash,),
        ).fetchone()
        return dict(row) if row else None

    def use(self, token_hash: str) -> str | None:
        """Mark a link used and return its user id, or None if it was already
        used or has expired. One statement, so a link can't be used twice."""
        row = self.db.execute(
            """UPDATE password_resets SET used_at = NOW()
               WHERE token_hash = %s AND used_at IS NULL AND expires_at > NOW()
               RETURNING user_id""",
            (token_hash,),
        ).fetchone()
        return row["user_id"] if row else None

    def delete_old(self, days: int = 7) -> None:
        self.db.execute(
            "DELETE FROM password_resets WHERE created_at < NOW() - make_interval(days => %s)",
            (days,),
        )
