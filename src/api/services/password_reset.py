# src/api/services/password_reset.py
#
# Forgotten passwords: a reset link is emailed to the account's address. The
# link works for RESET_TTL_MINUTES, once. Only a SHA-256 hash of its token is
# stored, so the table alone can't be used to reset anyone. The old password
# keeps working until the reset is finished, so asking for a link for someone
# else's account can't lock them out.
#
# Accounts with no email can't reset by themselves; an admin sets a password
# for them instead (/admin/users/{id}, "must change" ticked).

from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

from src.config import settings
from src.db.repositories.password_reset_repo import PasswordResetRepository

log = logging.getLogger(__name__)

RESET_TTL_MINUTES = 60
# Emails per account per hour, so nobody can flood someone's inbox.
MAX_PER_HOUR = 3
# Emails asked for from one IP per hour, across all accounts, so one machine
# can't send mail to everyone.
MAX_PER_IP_PER_HOUR = 10


@dataclass
class ResetEmail:
    to: str
    subject: str
    text: str


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def base_url(request_base_url: str) -> str | None:
    """Where links in emails point. Real email needs PUBLIC_BASE_URL: the
    request's own Host header can be faked to send a victim a link to
    someone else's site."""
    if settings.public_base_url:
        return settings.public_base_url.rstrip("/")
    if settings.smtp_host:
        log.error("PUBLIC_BASE_URL is not set, so no reset email was sent.")
        return None
    return request_base_url.rstrip("/")


def request_reset(
    conn, login: str, ip: str | None, request_base_url: str
) -> ResetEmail | None:
    """Make a reset link for the account named by username or email. Returns
    the email to send, or None when there is nothing to send: no such
    account, no email on file, or too many links in the last hour for the
    account or from the IP. Callers
    must answer the same way in every case."""
    login = login.strip()
    if not login:
        return None
    repo = PasswordResetRepository(conn)
    if ip and repo.recent_count_for_ip(ip, 60) >= MAX_PER_IP_PER_HOUR:
        return None
    account = repo.find_account(login)
    if not account or not account["email"]:
        return None
    if repo.recent_count(account["id"], 60) >= MAX_PER_HOUR:
        return None
    site = base_url(request_base_url)
    if site is None:
        return None

    token = secrets.token_urlsafe(32)
    repo.insert(account["id"], hash_token(token), RESET_TTL_MINUTES, ip)
    repo.delete_old()
    conn.commit()

    link = f"{site}/auth/reset?{urlencode({'token': token})}"
    return ResetEmail(
        to=account["email"],
        subject="Reset your Baseball GM password",
        text=(
            f"Someone, hopefully you, asked to reset the password for the Baseball GM "
            f"account {account['username']}.\n\n"
            f"Choose a new password here:\n{link}\n\n"
            f"The link works once, for the next {RESET_TTL_MINUTES} minutes.\n\n"
            f"If you didn't ask for this, ignore this email. Your password "
            f"hasn't changed.\n"
        ),
    )


def account_for_token(conn, token: str) -> dict | None:
    """The account (id, username) a link resets, if it still works."""
    if not token:
        return None
    return PasswordResetRepository(conn).find_valid(hash_token(token))


def use_token(conn, token: str) -> str | None:
    """Spend a link. Returns its user id, or None if it no longer works."""
    if not token:
        return None
    return PasswordResetRepository(conn).use(hash_token(token))
