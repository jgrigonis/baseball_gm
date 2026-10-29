# src/config.py

from __future__ import annotations

from typing import Literal

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

    # Outgoing email, for password reset links (src/api/services/mailer.py).
    # With no SMTP_HOST, emails are written to the server log instead of sent.
    # Port 465 uses SSL; any other port uses STARTTLS unless SMTP_STARTTLS is
    # false.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    mail_from: str = "GM Sim <noreply@localhost>"

    # The site's address as users reach it, e.g. "https://gm.example.com",
    # used to build links in emails. Required once SMTP_HOST is set: without
    # it, links would trust the request's Host header, which anyone can fake.
    public_base_url: str = ""

    # Who runs sims (src/api/services/sim_jobs.py). "separate": the sim worker
    # process (`python -m src.worker`), which must be running alongside the
    # web server. "inline": the web request that asks for one, with no worker;
    # the tests use this.
    sim_worker: Literal["separate", "inline"] = "separate"

    @property
    def served_over_https(self) -> bool:
        """Whether this is a real deployment, served over HTTPS, as
        PUBLIC_BASE_URL says. Cookies are then marked Secure, so browsers only
        send them over HTTPS, and the default admin password is refused. Off
        for plain http://localhost while developing."""
        return self.public_base_url.lower().startswith("https://")


settings = Settings()
