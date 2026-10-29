# The app's image: the web server, the sim worker and the migration step all
# run from it, with different commands (see docker-compose.yml).

FROM python:3.14-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/app/.venv/bin:$PATH

RUN pip install --no-cache-dir "uv>=0.11,<0.12"

WORKDIR /app

# Dependencies first, so a code change doesn't reinstall them.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY . .

# Run as an unprivileged user. Starting a league writes team CSVs.
RUN useradd --system --uid 1000 --home-dir /app app \
    && mkdir -p team_files logs temp_files \
    && chown app team_files logs temp_files
USER app

EXPOSE 8000

# The workers are WEB_CONCURRENCY processes. Forwarded headers are trusted
# from anywhere because only Caddy can reach this port: it isn't published
# outside the compose network.
CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
