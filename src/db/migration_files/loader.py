# src/db/migration_files/loader.py

import pkgutil
import importlib
import logging

import src.db.migration_files as migration_files

logger = logging.getLogger(__name__)


def load_migrations():
    """
    Load all migration modules and return sorted list of (version, upgrade_fn).

    Returns:
        list[tuple[int, callable]]: List of (version, upgrade_function) tuples,
                                     sorted by version number ascending.

    Raises:
        ValueError: If migration file is malformed (missing VERSION or upgrade)
        TypeError: If VERSION is not an integer or upgrade is not callable
    """
    migrations_list = []

    for module_info in pkgutil.iter_modules(migration_files.__path__):
        if module_info.name.startswith("migration_"):
            try:
                module = importlib.import_module(
                    f"{migration_files.__name__}.{module_info.name}"
                )

                # Validate VERSION exists and is an integer
                if not hasattr(module, "VERSION"):
                    raise ValueError(
                        f"Migration {module_info.name} missing VERSION constant"
                    )

                version = module.VERSION
                if not isinstance(version, int):
                    raise TypeError(
                        f"Migration {module_info.name} VERSION must be int, "
                        f"got {type(version).__name__}: {version}"
                    )

                # Validate upgrade exists and is callable
                if not hasattr(module, "upgrade"):
                    raise ValueError(
                        f"Migration {module_info.name} missing upgrade function"
                    )

                upgrade_fn = module.upgrade
                if not callable(upgrade_fn):
                    raise TypeError(
                        f"Migration {module_info.name} upgrade must be callable, "
                        f"got {type(upgrade_fn).__name__}"
                    )

                migrations_list.append((version, upgrade_fn))
                logger.debug(f"Loaded migration {module_info.name} (version {version})")

            except Exception as e:
                # Re-raise with more context
                raise RuntimeError(
                    f"Failed to load migration {module_info.name}: {e}"
                ) from e

    if not migrations_list:
        logger.info("No migrations found")
    else:
        logger.info(f"Loaded {len(migrations_list)} migration(s)")

    return sorted(migrations_list, key=lambda m: m[0])
