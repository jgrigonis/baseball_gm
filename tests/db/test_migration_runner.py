# tests/db/test_migration_runner.py

import pytest
from src.db.migration_files.runner import load_migrations


def test_load_migrations_returns_sorted_list():
    """Test that migrations are loaded and sorted by version."""
    migrations = load_migrations()

    # Should be a list of tuples
    assert isinstance(migrations, list)

    # Extract versions
    versions = [v for v, _ in migrations]

    # Should be sorted
    assert versions == sorted(versions)

    # All versions should be integers
    for version in versions:
        assert isinstance(version, int)


def test_load_migrations_functions_are_callable():
    """Test that all upgrade functions are callable."""
    migrations = load_migrations()

    for version, upgrade_fn in migrations:
        assert callable(upgrade_fn), f"Migration {version} upgrade is not callable"


def test_load_migrations_no_duplicates():
    """Test that no duplicate version numbers exist."""
    migrations = load_migrations()
    versions = [v for v, _ in migrations]

    assert len(versions) == len(set(versions)), "Duplicate migration versions found"
