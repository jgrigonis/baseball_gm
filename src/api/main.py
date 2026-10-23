# src/api/main.py

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import (
    http_exception_handler as default_http_exception_handler,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from src.api.routers import (
    auth,
    draft,
    games,
    history,
    leaders,
    leagues,
    lineup,
    players,
    playoffs,
    roster,
    seasons,
    sim,
    standings,
    stats,
    strategy,
)
from src.config import settings
from src.db.init import init_db
from src.db.connection import get_connection
from src.util.logger import configure_app_logging
from src.web.utils import templates

configure_app_logging(fmt="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Initializing database…")
    conn = get_connection()
    try:
        init_db(conn)
    finally:
        conn.close()
    yield


app = FastAPI(
    title="Baseball GM Sim",
    version="0.1.0",
    description="GM layer API — league management, strategic profiles, and drafts.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Web UI routers, one per area of the app.
for _module in (
    auth,
    leagues,
    draft,
    roster,
    sim,
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
):
    app.include_router(_module.router)

# Static files
app.mount(
    "/static",
    StaticFiles(directory=Path(__file__).resolve().parents[1] / "web" / "static"),
    name="static",
)


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": app.version}


# ── Error handling ────────────────────────────────────────────────────────────
#
# Routes don't catch exceptions themselves: they propagate through get_db,
# which rolls the transaction back, and end up here. Users get a short
# message; the traceback only goes to the server log.


def _error_response(request: Request, message: str, status_code: int):
    """A small HTML page for page loads and form posts, JSON for fetch/HTMX."""
    wants_html = "text/html" in request.headers.get("accept", "")
    if wants_html and request.headers.get("HX-Request") != "true":
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
    return await default_http_exception_handler(request, exc)


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """The services raise ValueError when an action breaks a game rule,
    e.g. simming a league that isn't in season. Show the user why."""
    log.info("Rejected %s %s: %s", request.method, request.url.path, exc)
    return _error_response(request, str(exc), 400)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _error_response(request, "Something went wrong.", 500)
