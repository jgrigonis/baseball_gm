# src/api/services/email_verify.py
#
# Verifying an email: a link is emailed to the account's address, and opening
# it sets users.is_verified and earns the Verified Email badge. It's
# optional; nothing else needs a verified email yet.
#
# Changing the email clears the verification and takes the badge back, until
# the new address is verified too. Each link remembers the address it went
# to, so a link sent before a change can't verify the new address.
#
# Like password resets (password_reset.py), only a SHA-256 hash of a link's
# token is stored. Opening the link spends it: unlike a reset, verifying
# changes nothing a mail scanner could hurt by opening it first, and the
# scanner only got the link by reading that inbox.

from __future__ import annotations

import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

from src.api.services import badges
from src.api.services.password_reset import base_url, hash_token

VERIFY_TTL_HOURS = 24
# Emails per account per hour, so nobody can flood an inbox with them.
MAX_PER_HOUR = 3
BADGE = "verified_email"


@dataclass
class VerifyEmail:
    to: str
    subject: str
    text: str


def request_link(
    conn, user_id: str, request_base_url: str
) -> tuple[VerifyEmail | None, str | None]:
    """Make a verify link for the account's current email. Returns the
    email to send, or an error to show the person instead."""
    user = conn.execute(
        "SELECT username, email, is_verified FROM users WHERE id = %s", (user_id,)
    ).fetchone()
    if not user or not user["email"]:
        return None, "Add an email first."
    if user["is_verified"]:
        return None, "That email is already verified."
    recent = conn.execute(
        """SELECT COUNT(*) AS n FROM email_verifications
           WHERE user_id = %s AND created_at > NOW() - INTERVAL '1 hour'""",
        (user_id,),
    ).fetchone()["n"]
    if recent >= MAX_PER_HOUR:
        return None, "Too many links sent in the last hour. Try again later."
    site = base_url(request_base_url)
    if site is None:
        return None, "Email isn't set up on this server."

    token = secrets.token_urlsafe(32)
    # A new link replaces any earlier one; its row stays to count toward the
    # hourly limit.
    conn.execute(
        """UPDATE email_verifications SET expires_at = NOW()
           WHERE user_id = %s AND used_at IS NULL AND expires_at > NOW()""",
        (user_id,),
    )
    conn.execute(
        """INSERT INTO email_verifications (user_id, email, token_hash, expires_at)
           VALUES (%s, %s, %s, NOW() + make_interval(hours => %s))""",
        (user_id, user["email"], hash_token(token), VERIFY_TTL_HOURS),
    )
    conn.execute(
        "DELETE FROM email_verifications WHERE created_at < NOW() - INTERVAL '7 days'"
    )

    link = f"{site}/account/verify-email?{urlencode({'token': token})}"
    return VerifyEmail(
        to=user["email"],
        subject="Verify your Baseball GM email",
        text=(
            f"To verify this email for the Baseball GM account "
            f"{user['username']}, open this link:\n{link}\n\n"
            f"The link works once, for the next {VERIFY_TTL_HOURS} hours.\n\n"
            f"If you don't have a Baseball GM account, ignore this email.\n"
        ),
    ), None


def verify(conn, token: str) -> str | None:
    """Spend a link and verify the address it went to, if it's still the
    account's email. Returns the user id, or None if the link doesn't work."""
    if not token:
        return None
    row = conn.execute(
        """UPDATE email_verifications SET used_at = NOW()
           WHERE token_hash = %s AND used_at IS NULL AND expires_at > NOW()
           RETURNING user_id, email""",
        (hash_token(token),),
    ).fetchone()
    if not row:
        return None
    user = conn.execute(
        """UPDATE users SET is_verified = TRUE
           WHERE id = %s AND lower(email) = lower(%s)
           RETURNING id""",
        (row["user_id"], row["email"]),
    ).fetchone()
    if not user:
        return None  # The email has changed since the link was sent.
    badges.award(conn, user["id"])
    return user["id"]


def email_changed(conn, user_id: str) -> None:
    """After the account's email changed (or was removed): the old
    verification no longer counts, so the badge goes and old links stop
    working. is_verified itself is cleared by UserRepository.set_email."""
    badges.take_back(conn, user_id, BADGE)
    conn.execute(
        """UPDATE email_verifications SET expires_at = NOW()
           WHERE user_id = %s AND used_at IS NULL AND expires_at > NOW()""",
        (user_id,),
    )
