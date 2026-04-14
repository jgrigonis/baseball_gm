# src/db/repositories/user_repo.py
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

        self.db.execute(
            "INSERT INTO users (id, session_token, display_name) VALUES (%s, %s, %s)",
            (user_id, token, display_name or "Guest"),
        )
