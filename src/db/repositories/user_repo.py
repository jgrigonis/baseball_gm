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
                   is_admin, is_contributor, must_change_password, dismissed_tips, turn_emails,
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

    def record_login(self, user_id: str) -> None:
        """Note that the user just signed in (and so was seen)."""
        self.db.execute(
            "UPDATE users SET last_login_at = NOW(), last_seen_at = NOW() WHERE id = %s",
            (user_id,),
        )

    # How stale last_seen_at gets before a page load writes it again.
    SEEN_EVERY = "5 minutes"

    def record_seen(self, user_id: str) -> None:
        """Note that the user just loaded a page (shown on /admin/users).
        Written at most every SEEN_EVERY, and skipped if another request of
        theirs holds the row, so a long sim never makes a page wait."""
        self.db.execute(
            f"""UPDATE users SET last_seen_at = NOW()
                WHERE id = (SELECT id FROM users
                            WHERE id = %s
                              AND (last_seen_at IS NULL
                                   OR last_seen_at < NOW() - INTERVAL '{self.SEEN_EVERY}')
                            FOR UPDATE SKIP LOCKED)""",
            (user_id,),
        )

    def username_taken(self, username: str, other_than: str | None = None) -> bool:
        row = self.db.execute(
            """SELECT 1 FROM users
               WHERE lower(username) = lower(%s) AND id IS DISTINCT FROM %s""",
            (username, other_than),
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

    def rename(self, user_id: str, old: str, new: str) -> None:
        """Change someone's login name. Their display name, and their name as
        a GM in each league, follow it when they were still the old login
        name. Sessions are keyed by token, so nobody is signed out."""
        self.db.execute(
            """UPDATE users
               SET username = %s,
                   display_name = CASE WHEN display_name = %s THEN %s
                                       ELSE display_name END
               WHERE id = %s""",
            (new, old, new, user_id),
        )
        self.db.execute(
            """UPDATE gms SET display_name = %s
               WHERE user_id = %s AND display_name = %s AND NOT is_ai""",
            (new, user_id, old),
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
            """SELECT id, display_name, username, email, is_verified, is_admin,
                      is_contributor, must_change_password, created_at, last_login_at, last_seen_at,
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
            """SELECT u.id, u.display_name, u.username, u.email, u.is_verified, u.is_admin,
                      u.must_change_password, u.created_at, u.last_seen_at,
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

    def set_email(self, user_id: str, email: str | None) -> bool:
        """Set the email. A different address (ignoring case) is no longer
        verified. Returns whether the address changed."""
        row = self.db.execute(
            """UPDATE users u SET email = %s,
                      is_verified = u.is_verified
                                    AND lower(old.email) IS NOT DISTINCT FROM lower(%s)
               FROM users old
               WHERE u.id = %s AND old.id = u.id
               RETURNING lower(old.email) IS DISTINCT FROM lower(%s) AS changed""",
            (email, email, user_id, email),
        ).fetchone()
        return bool(row and row["changed"])

    def set_turn_emails(self, user_id: str, on: bool) -> None:
        """Whether they get an email when a league is waiting on them
        (src/api/services/turn_alerts.py)."""
        self.db.execute(
            "UPDATE users SET turn_emails = %s WHERE id = %s", (on, user_id)
        )

    def set_profile(
        self, user_id: str, bio: str | None, favorite_team: str | None
    ) -> None:
        """The bio and favorite team on their GM profile."""
        self.db.execute(
            "UPDATE users SET bio = %s, favorite_team = %s WHERE id = %s",
            (bio, favorite_team, user_id),
        )

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
