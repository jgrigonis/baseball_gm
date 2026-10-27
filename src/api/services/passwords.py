# src/api/services/passwords.py
#
# Password hashing (argon2id via argon2-cffi) and the rules for usernames,
# passwords and emails. Kept apart from the routes so the rules have one home.

from __future__ import annotations

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()

# Verified against when the username doesn't exist, so a wrong username takes
# as long as a wrong password and response time doesn't reveal which names
# are registered.
_DUMMY_HASH = _hasher.hash("not-a-real-password")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,30}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 8
MAX_PASSWORD_LEN = 128


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """True if password matches. A missing hash never matches."""
    try:
        matched = _hasher.verify(password_hash or _DUMMY_HASH, password)
    except VerificationError, InvalidHashError:
        return False
    return matched and password_hash is not None


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def username_error(username: str) -> str | None:
    if not USERNAME_RE.match(username):
        return "Usernames are 3–30 letters, numbers, dots, dashes or underscores."
    return None


def password_error(password: str, confirm: str) -> str | None:
    if len(password) < MIN_PASSWORD_LEN:
        return f"Passwords need at least {MIN_PASSWORD_LEN} characters."
    if len(password) > MAX_PASSWORD_LEN:
        return f"Passwords can be at most {MAX_PASSWORD_LEN} characters."
    if password != confirm:
        return "The passwords don't match."
    return None


def clean_email(email: str) -> tuple[str | None, str | None]:
    """(email, error). A blank email means none."""
    email = email.strip()
    if not email:
        return None, None
    if len(email) > 254 or not EMAIL_RE.match(email):
        return None, "That doesn't look like an email address."
    return email, None
