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
                   password_hash IS NOT NULL AS has_password
            FROM users
            WHERE session_token = %s
            """,
            (token,),
        ).fetchone()

        return dict(row) if row else None

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

    def insert_user(self, user_id, token, display_name, username, password_hash):
        """Insert a user in the users table."""
        self.db.execute(
            """
            INSERT INTO users (id, session_token, display_name, username, password_hash)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, token, display_name, username, password_hash),
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
