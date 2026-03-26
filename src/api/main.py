# src/api/main.py

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.api.routers import draft, gms, leagues, sim
from src.config import settings
from src.db.init import init_db
from src.db.connection import get_connection

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run DB migrations on startup, nothing special on shutdown."""
    log.info("Running migrations against %s…", settings.db_path)
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

app.include_router(leagues.router)
app.include_router(gms.router)
app.include_router(draft.router)
app.include_router(sim.router)

app.mount("/static", StaticFiles(directory="."), name="static")


@app.get("/health", tags=["meta"])
def health() -> dict:
    return {"status": "ok", "version": app.version}
