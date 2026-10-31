# src/db/repositories/user_repo.py
import uuid


class UserRepository:
    def __init__(self, db):
        self.db = db

    def get_by_token(self, token: str | None) -> dict | None:
        """
        return a user dictionary from their row, based on their token.
        """
        if not token:
            return None

        row = self.db.execute(
            """
            SELECT id, display_name, username, email, is_verified, created_at,
                   is_admin, must_change_password, dismissed_tips,
                   password_hash IS NOT NULL AS has_password
            FROM users
            WHERE session_token = %s
            """,
            (token,),
        ).fetchone()

        return dict(row) if row else None

    def dismiss_tip(self, user_id: str, tip: str) -> None:
        """Stop showing one of the first-visit tab tips to this user."""
        self.db.execute(
            """UPDATE users SET dismissed_tips = array_append(dismissed_tips, %s)
               WHERE id = %s AND NOT (%s = ANY(dismissed_tips))""",
            (tip, user_id, tip),
        )

    def reset_tips(self, user_id: str) -> None:
        """Show every first-visit tab tip again."""
        self.db.execute(
            "UPDATE users SET dismissed_tips = '{}' WHERE id = %s", (user_id,)
        )

    def get_login(self, username: str) -> dict | None:
        """Return id, session_token and password_hash for a username (any case)."""
        row = self.db.execute(
            """
            SELECT id, session_token, password_hash
            FROM users
            WHERE lower(username) = lower(%s)
            """,
            (username,),
        ).fetchone()
        return dict(row) if row else None

    def username_taken(self, username: str) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM users WHERE lower(username) = lower(%s)", (username,)
        ).fetchone()
        return row is not None

    def insert_user(
        self,
        user_id,
        token,
        display_name,
        username,
        password_hash,
        email=None,
        is_admin=False,
        must_change_password=False,
    ):
        """Insert a user in the users table."""
        self.db.execute(
            """
            INSERT INTO users (id, session_token, display_name, username,
                               password_hash, email, is_admin, must_change_password)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                token,
                display_name,
                username,
                password_hash,
                email,
                is_admin,
                must_change_password,
            ),
        )

    def set_credentials(self, user_id, username, password_hash, token):
        """Give a passwordless (legacy guest) user a login and a fresh session."""
        self.db.execute(
            """
            UPDATE users
            SET username = %s, password_hash = %s, session_token = %s
            WHERE id = %s
            """,
            (username, password_hash, token, user_id),
        )

    def set_password_hash(self, user_id, password_hash):
        self.db.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (password_hash, user_id),
        )

    def set_password(self, user_id, password_hash, token, must_change: bool):
        """A new password and a fresh session, which signs out every browser
        using the old one. Unused reset links for the account stop working."""
        self.db.execute(
            """UPDATE users
               SET password_hash = %s, session_token = %s, must_change_password = %s
               WHERE id = %s""",
            (password_hash, token, must_change, user_id),
        )
        self.db.execute(
            "DELETE FROM password_resets WHERE user_id = %s AND used_at IS NULL",
            (user_id,),
        )

    def set_session_token(self, user_id, token):
        self.db.execute(
            "UPDATE users SET session_token = %s WHERE id = %s", (token, user_id)
        )

    def invalidate_session(self, user_id):
        """Log the user out by setting a garbage token for their session."""
        # Generate a new random token that the user doesn't have
        # This makes the old cookie value invalid
        new_garbage_token = uuid.uuid4().hex
        self.db.execute(
            "UPDATE users SET session_token = %s WHERE id = %s",
            (new_garbage_token, user_id),
        )

    # ── Admin ─────────────────────────────────────────────────────────────────

    def get_by_id(self, user_id: str) -> dict | None:
        row = self.db.execute(
            """SELECT id, display_name, username, email, is_admin, is_contributor,
                      must_change_password, created_at,
                      password_hash IS NOT NULL AS has_password
               FROM users WHERE id = %s""",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_by_username(self, username: str) -> dict | None:
        row = self.db.execute(
            "SELECT id, username, is_admin FROM users WHERE lower(username) = lower(%s)",
            (username,),
        ).fetchone()
        return dict(row) if row else None

    def list_all(self) -> list[dict]:
        """Every user, with how many leagues they're a GM in."""
        rows = self.db.execute(
            """SELECT u.id, u.display_name, u.username, u.email, u.is_admin,
                      u.must_change_password, u.created_at,
                      u.password_hash IS NOT NULL AS has_password,
                      (SELECT COUNT(*) FROM gms g WHERE g.user_id = u.id) AS leagues
               FROM users u
               ORDER BY u.is_admin DESC, lower(coalesce(u.username, u.display_name))"""
        ).fetchall()
        return [dict(r) for r in rows]

    def email_taken(self, email: str, other_than: str | None = None) -> bool:
        row = self.db.execute(
            "SELECT 1 FROM users WHERE lower(email) = lower(%s) AND id IS DISTINCT FROM %s",
            (email, other_than),
        ).fetchone()
        return row is not None

    def set_email(self, user_id: str, email: str | None) -> None:
        self.db.execute("UPDATE users SET email = %s WHERE id = %s", (email, user_id))

    def set_contributor(self, user_id: str, is_contributor: bool) -> None:
        self.db.execute(
            "UPDATE users SET is_contributor = %s WHERE id = %s",
            (is_contributor, user_id),
        )

    def set_admin(self, user_id: str, is_admin: bool) -> None:
        self.db.execute(
            "UPDATE users SET is_admin = %s WHERE id = %s", (is_admin, user_id)
        )

    def admin_count(self) -> int:
        return self.db.execute(
            "SELECT COUNT(*) AS n FROM users WHERE is_admin"
        ).fetchone()["n"]

    def delete(self, user_id: str) -> None:
        self.db.execute("DELETE FROM users WHERE id = %s", (user_id,))
