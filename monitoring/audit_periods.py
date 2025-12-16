"""
audit_periods.py
Check which FSN periods exist, which are missing, and which have incomplete data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Sequence, Tuple

from secfsn.config.core import DATA_DIR

Period = Tuple[int, int]

# TXT is intentionally excluded because the pipeline does not currently convert it.
REQUIRED_FILES: Sequence[str] = [
    "sub.parquet",
    "num.parquet",
    "pre.parquet",
    "tag.parquet",
]


def _iter_period_dirs(data_dir: Path) -> Iterable[Tuple[Period, Path]]:
    """
    Yield ((year, quarter), Path) for each period-like subdirectory under data_dir.
    Expected folder names: 'YYYY_Q' (e.g. '2020_4', '2024_1').
    """
    for child in sorted(data_dir.iterdir()):
        if not child.is_dir():
            continue
        parts = child.name.split("_")
        if len(parts) != 2:
            continue
        try:
            year = int(parts[0])
            quarter = int(parts[1])
        except ValueError:
            continue
        yield (year, quarter), child


def audit_available_periods(
    data_dir: Path | None = None,
    required_files: Sequence[str] = REQUIRED_FILES,
) -> Dict[Period, Dict]:
    """
    Inspect data_dir for FSN period folders and report which have complete parquet data.

    Returns:
        dict keyed by (year, quarter) with:
            {
                "exists": bool,
                "complete": bool,
                "missing_files": [str, ...],
            }
    """
    base = data_dir or DATA_DIR
    results: Dict[Period, Dict] = {}

    for (year, quarter), period_dir in _iter_period_dirs(base):
        parquet_dir = period_dir / "parquet"
        exists = parquet_dir.exists()
        missing = []

        if exists:
            for req in required_files:
                if not (parquet_dir / req).exists():
                    missing.append(req)

        results[(year, quarter)] = {
            "exists": exists,
            "complete": exists and len(missing) == 0,
            "missing_files": missing,
        }

    return results
