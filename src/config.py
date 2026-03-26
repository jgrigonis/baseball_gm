# src/config.py

from __future__ import annotations
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from src.util.locations import LEAGUE_FILES_DIR


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    db_path: str = str(Path(LEAGUE_FILES_DIR) / "league.db")

    # Space-separated list, e.g. "http://localhost:5173 http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Set to True only in dev — exposes raw skill integers on player endpoints
    debug_mode: bool = False


settings = Settings()
