"""
validate_files.py
Tests whether parquet files can be read without corruption.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import polars as pl

from secfsn.config.core import DATA_DIR


def validate_parquet_files(data_dir: Path | None = None) -> List[str]:
    """
    Validate parquet files for all periods under `data_dir`.

    Returns:
        list of error messages. Empty list => no issues detected.
    """
    base = data_dir or DATA_DIR
    errors: List[str] = []

    if not base.exists():
        return [f"Data directory does not exist: {base}"]

    for period in base.iterdir():
        if not period.is_dir():
            continue

        pq_dir = period / "parquet"
        if not pq_dir.exists():
            continue

        for file in pq_dir.glob("*.parquet"):
            try:
                # Use lazy scan + small head to avoid loading full tables.
                pl.scan_parquet(str(file)).head(5).collect()
            except Exception as e:
                errors.append(f"{file}: {e}")

    return errors
