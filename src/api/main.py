# src/api/main.py

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import (
    http_exception_handler as default_http_exception_handler,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.api.routers import (
    admin,
    all_star,
    auth,
    draft,
    games,
    history,
    leaders,
    leagues,
    lineup,
    players,
    playoffs,
    profiles,
    ready,
    roster,
    seasons,
    sim,
    standings,
    stats,
    strategy,
    trades,
    tutorial,
    uniforms,
)
from src.api.dependencies import NotLeagueGM, PasswordChangeRequired
from src.config import settings
from src.db.connection import get_connection
from src.db.locks import LeagueBusy
from src.db.migrations import pending_migrations
from src.util.logger import configure_app_logging
from src.web.utils import templates

configure_app_logging(fmt="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


class _QuietPolls(logging.Filter):
    """Leave the pages' background polls (the ready bar, a viewer's refresh,
    the lobby's GM list) out of the access log while they succeed. Failures
    are still logged."""

    POLLS = re.compile(r"^/leagues/[^/]+/(sim/status|progress|lobby/gms)$")

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn.access args: (client, method, path, http_version, status)
        args = record.args
        if isinstance(args, tuple) and len(args) == 5:
            path, status = str(args[2]).split("?")[0], args[4]
            if self.POLLS.match(path) and isinstance(status, int) and status < 300:
                return False
        return True


logging.getLogger("uvicorn.access").addFilter(_QuietPolls())


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.smtp_host and not settings.public_base_url:
        # Reset emails would have no address to link to (password_reset.py).
        raise RuntimeError("SMTP_HOST is set, so PUBLIC_BASE_URL must be too.")
    # Migrations are a separate step (src/db/migrate.py), run once before
    # the server starts, rather than by each worker process at once.
    conn = get_connection()
    try:
        pending = pending_migrations(conn)
    finally:
        conn.close()
    if pending:
        raise RuntimeError(
            "The database has migrations to apply: "
            + ", ".join(str(v) for v in pending)
            + ". Run `uv run python -m src.db.migrate` first."
        )
    yield


app = FastAPI(
    title="Baseball GM",
    # This version is updated manually when the API changes in a way that breaks old clients.
    # It is not the same as the version in pyproject.toml, which is updated for every release.
    version="0.1.0",
    description="GM layer API — league management, strategic profiles, and drafts.",
    lifespan=lifespan,
)

if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ── Cross-site request check (CSRF) ───────────────────────────────────────────
#
# The session cookie is SameSite=Lax, which keeps other sites from posting
# with it, but SameSite counts every subdomain of the same domain as one
# site, and it doesn't cover the login form, which needs no cookie. Browsers
# send an Origin header with every POST, so any request that changes
# something must come from the site's own pages. Requests with neither
# Origin nor Referer aren't from a browser form or fetch (curl, the tests)
# and pass: they can't carry a victim's cookie.

_SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}


def _origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


def _allowed_origins(request: Request) -> set[str]:
    # The address the request was sent to: a browser on another site can't
    # set the Host header, so a matching Origin means the site's own page.
    # This is what lets a local server run with the deployed .env (e.g.
    # browsing http://127.0.0.1:8000 with PUBLIC_BASE_URL set to the real
    # site). PUBLIC_BASE_URL is allowed too, in case a proxy rewrites Host.
    sites = [str(request.base_url), *settings.cors_origins]
    if settings.public_base_url:
        sites.append(settings.public_base_url)
    return {_origin_of(s) for s in sites}


def is_cross_site(request: Request) -> bool:
    if request.method in _SAFE_METHODS:
        return False
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer")
        if referer is None:
            return False
        origin = referer
    # "null" (sandboxed frames, privacy redirects) never matches.
    return _origin_of(origin) not in _allowed_origins(request)


@app.middleware("http")
async def reject_cross_site_requests(request: Request, call_next):
    if is_cross_site(request):
        log.warning(
            "Rejected cross-site %s %s from %s",
            request.method,
            request.url.path,
            request.headers.get("origin") or request.headers.get("referer"),
        )
        return _error_response(request, "That request came from another site.", 403)
    return await call_next(request)


# Web UI routers, one per area of the app.
for _module in (
    auth,
    leagues,
    draft,
    roster,
    sim,
    ready,
    standings,
    leaders,
    lineup,
    strategy,
    stats,
    playoffs,
    games,
    seasons,
    history,
    players,
    admin,
    tutorial,
    trades,
    all_star,
    uniforms,
    profiles,
):
    app.include_router(_module.router)

# Static files
STATIC_DIR = Path(__file__).resolve().parents[1] / "web" / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    # Pages link the SVG icon; this answers browsers and tools that ask for
    # /favicon.ico directly, e.g. when opening a JSON endpoint.
    return FileResponse(STATIC_DIR / "img" / "apple-touch-icon.png")


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": app.version}


# ── Error handling ────────────────────────────────────────────────────────────
#
# Routes don't catch exceptions themselves: they propagate through get_db,
# which rolls the transaction back, and end up here. Users get a short
# message; the traceback only goes to the server log.


def _wants_page(request: Request) -> bool:
    """A browser loading a page or posting a form, not fetch/HTMX."""
    wants_html = "text/html" in request.headers.get("accept", "")
    return wants_html and request.headers.get("HX-Request") != "true"


def _error_response(request: Request, message: str, status_code: int):
    """A small HTML page for page loads and form posts, JSON for fetch/HTMX."""
    if _wants_page(request):
        return templates.TemplateResponse(
            request,
            "error.html",
            {"message": message, "status_code": status_code},
            status_code=status_code,
        )
    return JSONResponse({"detail": message}, status_code=status_code)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse("/")
    if isinstance(exc, PasswordChangeRequired) and _wants_page(request):
        return RedirectResponse("/auth/change-password", status_code=303)
    if (
        isinstance(exc, NotLeagueGM)
        and request.method == "GET"
        and _wants_page(request)
    ):
        # A league page for a league this user isn't in, or one that was
        # deleted (e.g. a bookmark, or a refresh after a reset).
        return RedirectResponse("/leagues/", status_code=303)
    return await default_http_exception_handler(request, exc)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """The services raise ValueError when an action breaks a game rule,
    e.g. simming a league that isn't in season. Show the user why."""
    log.info("Rejected %s %s: %s", request.method, request.url.path, exc)
    return _error_response(request, str(exc), 400)


@app.exception_handler(LeagueBusy)
async def league_busy_handler(request: Request, exc: LeagueBusy):
    """Two requests tried to advance the same league at once (another tab, or
    another GM). The first one keeps going; tell the second why it stopped."""
    log.info("Rejected %s %s: %s", request.method, request.url.path, exc)
    return _error_response(request, str(exc), 409)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _error_response(request, "Something went wrong.", 500)
