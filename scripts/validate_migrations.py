# scripts/validate_migrations.py

"""
Validate all migration files are well-formed.
Run this in CI to catch issues early.
"""

from src.db.migration_files.loader import load_migrations


def main():
    print("Validating migrations...")

    try:
        migrations = load_migrations()

        print(f"✓ Found {len(migrations)} valid migration(s)")

        for version, upgrade_fn in migrations:
            print(f"  - Migration {version:03d}: {upgrade_fn.__name__}")

        print("\n✓ All migrations valid!")
        return 0

    except Exception as e:
        print(f"\n✗ Migration validation failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
