# src/api/main.py

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

# from src.api.routers import draft, gms, leagues, web
from src.api.routers import web
from src.config import settings
from src.db.init import init_db
from src.db.connection import get_connection

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

# Web UI router registered FIRST — its specific routes like /leagues/new
# and /leagues/join must take priority over the API's /leagues/{join_code}
# wildcard, which would otherwise swallow them.
app.include_router(web.router)

# dead routers
# JSON API routers
# app.include_router(leagues.router)
# app.include_router(gms.router)
# app.include_router(draft.router)

# Static files
app.mount("/static", StaticFiles(directory="src/web/static"), name="static")


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": app.version}

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse("/")
    raise exc
