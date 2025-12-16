"""
integrity.py
Basic integrity checks for FSN parquet data.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Tuple

import polars as pl

from secfsn.config.core import DATA_DIR
from secfsn.common.logging_utils import get_logger
from secfsn.monitoring.audit_periods import _iter_period_dirs

logger = get_logger("monitoring_integrity")


def validate_sub_file(path: Path) -> Dict[str, Any]:
    """
    Checks SUB file for obvious issues:
      - missing CIK / name
      - (optional) reports duplicate CIK count as a warning

    Note: Multiple filings per CIK in a period are normal, so duplicates
    are reported as 'warnings' only, not as hard issues.
    """
    if not path.exists():
        return {"file": str(path), "status": "NOT_FOUND", "issues": [], "warnings": []}

    df = pl.read_parquet(str(path))

    issues = []
    warnings = []

    if "cik" in df.columns and df["cik"].null_count() > 0:
        issues.append("null_cik")

    if "name" in df.columns and df["name"].null_count() > 0:
        issues.append("null_name")

    if "cik" in df.columns:
        dup_count = (
            df.select(pl.col("cik").is_duplicated().sum())
            .to_series()
            .item()
        )
        if dup_count > 0:
            warnings.append(f"duplicate_cik ({int(dup_count)})")

    return {
        "file": str(path),
        "status": "OK" if not issues else "ISSUES",
        "issues": issues,
        "warnings": warnings,
    }


def validate_numeric_file(path: Path) -> Dict[str, Any]:
    """
    Checks NUM file for basic structural sanity.

    We do NOT treat null 'value' as an error because missing values are
    common in SEC data. Instead we report simple null counts as metadata.
    """
    if not path.exists():
        return {"file": str(path), "status": "NOT_FOUND", "issues": [], "meta": {}}

    df = pl.read_parquet(str(path))

    issues = []
    meta: Dict[str, Any] = {}

    if "value" not in df.columns:
        issues.append("missing_value_column")
    else:
        meta["null_value_count"] = int(df["value"].null_count())

    if "ddate" in df.columns:
        meta["null_ddate_count"] = int(df["ddate"].null_count())

    return {
        "file": str(path),
        "status": "OK" if not issues else "ISSUES",
        "issues": issues,
        "meta": meta,
    }


def run_integrity_checks(data_dir: Path | None = None) -> Dict[str, Dict[str, Any]]:
    """
    Run integrity checks for all periods in `data_dir`.

    Returns:
        {
            "YYYY_Q": {
                "sub": {...},
                "num": {...},
            },
            ...
        }
    """
    base = data_dir or DATA_DIR
    results: Dict[str, Dict[str, Any]] = {}

    for (year, quarter), period_dir in _iter_period_dirs(base):
        period_key = f"{year}_{quarter}"
        parquet_dir = period_dir / "parquet"

        sub_path = parquet_dir / "sub.parquet"
        num_path = parquet_dir / "num.parquet"

        results[period_key] = {
            "sub": validate_sub_file(sub_path),
            "num": validate_numeric_file(num_path),
        }

    return results
