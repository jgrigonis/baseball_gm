# src/util/locations.py

from pathlib import Path

# Repo root, so these paths work no matter which directory the process starts in.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

TEMP_FILES = PROJECT_ROOT / "temp_files"
LOG_FILES = PROJECT_ROOT / "logs"
