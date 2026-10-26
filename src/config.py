# src/config.py

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from src.util.locations import PROJECT_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8"
    )

    # Space-separated list, e.g. "http://localhost:5173 http://localhost:3000"
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Set to True only in dev — exposes raw skill integers on player endpoints
    debug_mode: bool = False

    # The default admin's password, until they change it at first sign-in
    # (see migration 010). Set ADMIN_INITIAL_PASSWORD before the first start
    # if the server is reachable by anyone else.
    admin_initial_password: str = "changeme"


settings = Settings()
