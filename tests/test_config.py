# tests/test_config.py

from src.config import Settings


def test_env_file_from_env_example_loads(tmp_path):
    """A .env copied from .env.example also carries names only Docker Compose
    reads; the app must still start with it."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "POSTGRES_PASSWORD=anything-local\n"
        "WEB_CONCURRENCY=2\n"
        "BACKUP_HOUR=3\n"
        "BACKUP_KEEP_DAYS=14\n"
        "SMTP_PORT=2587\n"
    )

    settings = Settings(_env_file=env_file)

    assert settings.smtp_port == 2587
    assert not hasattr(settings, "postgres_password")
