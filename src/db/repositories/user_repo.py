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
            SELECT id, display_name, email, is_verified, created_at 
            FROM users 
            WHERE session_token = %s
            """,
            (token,),
        ).fetchone()

        return dict(row) if row else None

    def insert_user(self, user_id, token, display_name):
        """Insert a user in the users table."""
        self.db.execute(
            "INSERT INTO users (id, session_token, display_name) VALUES (%s, %s, %s)",
            (user_id, token, display_name or "Guest"),
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
