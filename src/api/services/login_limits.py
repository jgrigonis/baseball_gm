# src/api/services/login_limits.py
#
# Turning away password guessing at sign-in. Every wrong password is recorded
# in login_failures (Postgres, so the counts survive restarts and are shared
# by every worker process). Too many recent failures for one username, or from
# one IP, and sign-in is refused for a while without checking the password.
#
# Unknown usernames count the same as real ones, so the answer never says
# whether an account exists. Someone who locks out another person's account
# by guessing at it doesn't lock the owner out for good: the limit lifts on
# its own, and an emailed reset link still works meanwhile.
#
# The forgot-password limits live in services/password_reset.py.

from __future__ import annotations

import math

from fastapi import Request

from src.db.repositories.login_failure_repo import LoginFailureRepository

WINDOW_MINUTES = 15
# Failures in the window before sign-in is refused.
MAX_PER_ACCOUNT = 10
MAX_PER_IP = 30


def client_ip(request: Request) -> str | None:
    """The visitor's IP. Behind nginx this is only right if nginx sets
    X-Forwarded-For and the server trusts it from nginx's address (uvicorn's
    and gunicorn's forwarded_allow_ips; see README)."""
    return request.client.host if request.client else None


def _key(username: str) -> str:
    return username.strip().lower()


def minutes_blocked(conn, username: str, ip: str | None) -> int:
    """Minutes until this username can try again from this IP; 0 if it can
    now."""
    repo = LoginFailureRepository(conn)
    wait = repo.seconds_blocked(
        "username", _key(username), MAX_PER_ACCOUNT, WINDOW_MINUTES
    )
    if ip:
        wait = max(wait, repo.seconds_blocked("ip", ip, MAX_PER_IP, WINDOW_MINUTES))
    return math.ceil(wait / 60)


def record_failure(conn, username: str, ip: str | None) -> None:
    repo = LoginFailureRepository(conn)
    repo.add(_key(username), ip)
    repo.delete_old()


def clear(conn, username: str) -> None:
    """Forget an account's failures once its owner signs in."""
    LoginFailureRepository(conn).clear(_key(username))
