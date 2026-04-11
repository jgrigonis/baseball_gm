# src/config.py

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Space-separated list, e.g. "http://localhost:5173 http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Set to True only in dev — exposes raw skill integers on player endpoints
    debug_mode: bool = False


settings = Settings()
