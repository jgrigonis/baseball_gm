# src/types/rows.py
from typing import Any
from collections.abc import Mapping

CsvRow = Mapping[str, str]
DbRow = Mapping[str, Any]
