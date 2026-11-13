# tests/db/test_migration_loader.py

from src.db.migration_files.loader import load_migrations


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


def test_every_migration_has_its_own_version():
    """Two migrations with one VERSION: a database records only one of them,
    so the other never runs there, or the second insert into
    schema_migrations fails (migrations 123-125, 2026-11-13)."""
    import pkgutil
    import importlib

    import src.db.migration_files as files

    seen: dict[int, str] = {}
    for info in pkgutil.iter_modules(files.__path__):
        if not info.name.startswith("migration_"):
            continue
        version = importlib.import_module(f"{files.__name__}.{info.name}").VERSION
        assert version not in seen, (
            f"{info.name} and {seen[version]} are both {version}"
        )
        seen[version] = info.name
