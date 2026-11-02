#!/usr/bin/env bash
# Pull the latest code, then rebuild and restart the Docker containers.
set -euo pipefail

cd "$(dirname "$0")"

echo "Pulling latest changes..."
if ! git pull; then
    echo "Error: git pull failed. Not rebuilding containers." >&2
    exit 1
fi

echo "Rebuilding and starting containers..."
docker compose up -d --build
