import pkgutil
import importlib

import src.db.migration_files as migration_files


def load_migrations():
    migrations_list = []

    for module_info in pkgutil.iter_modules(migration_files.__path__):
        if module_info.name.startswith("migration_"):
            module = importlib.import_module(
                f"{migration_files.__name__}.{module_info.name}"
            )
            migrations_list.append((module.VERSION, module.upgrade))

    return sorted(migrations_list, key=lambda m: m[0])
