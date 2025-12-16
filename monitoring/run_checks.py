"""
Unified runner for all monitoring checks.

This module aggregates:
- audit of available FSN periods
- parquet file-level validation
- fundamentals validation (via Polars engine)
- basic integrity checks (SUB/NUM)
- lightweight performance snapshot

Use:
    from secfsn.monitoring.run_checks import run_all_checks
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from secfsn.config.core import DATA_DIR
from secfsn.common.logging_utils import get_logger
from secfsn.monitoring.audit_periods import audit_available_periods, _iter_period_dirs
from secfsn.monitoring.validate_files import validate_parquet_files
from secfsn.monitoring.validate_fundamentals import validate_fundamentals_dataset
from secfsn.monitoring.integrity import run_integrity_checks
from secfsn.engine.polars_engine import build_fundamentals_polars_multi_pandas


logger = get_logger("monitoring_run_checks")

Period = Tuple[int, int]


def _select_sample_periods(data_dir: Path, max_periods: int = 4) -> List[Period]:
    """
    Helper: pick up to `max_periods` existing FSN periods from `data_dir`.
    Used for fundamentals/performance checks to keep runtime bounded.
    """
    periods: List[Period] = []
    for (year, quarter), _dir in _iter_period_dirs(data_dir):
        periods.append((year, quarter))
    periods.sort()
    if not periods:
        return []
    return periods[:max_periods]


def _compute_fundamentals_check(data_dir: Path) -> Dict[str, Any]:
    """
    Build a small multi-period fundamentals panel using the Polars engine
    and run structural validation on it.
    """
    sample_periods = _select_sample_periods(data_dir)
    if not sample_periods:
        return {"status": "NO_DATA", "detail": "No FSN periods found."}

    try:
        df = build_fundamentals_polars_multi_pandas(
            periods=sample_periods,
            base_dir=data_dir,
        )
    except Exception as e:
        logger.exception("Error while building fundamentals panel for monitoring.")
        return {"status": "ERROR", "error": str(e), "periods": sample_periods}

    errors = validate_fundamentals_dataset(df)
    if errors:
        return {
            "status": "ISSUES",
            "errors": errors,
            "rows": int(len(df)),
            "periods": sample_periods,
        }
    else:
        return {
            "status": "OK",
            "rows": int(len(df)),
            "periods": sample_periods,
        }


def _performance_snapshot(data_dir: Path) -> Dict[str, Any]:
    """
    Lightweight performance snapshot: row counts for core parquet tables
    for a small sample of periods.
    """
    try:
        import polars as pl
    except Exception:
        # If Polars is not available for some reason, skip performance snapshot.
        return {"status": "SKIPPED", "reason": "polars not available"}

    sample_periods = _select_sample_periods(data_dir, max_periods=3)
    if not sample_periods:
        return {"status": "NO_DATA"}

    snapshot: Dict[str, Any] = {"status": "OK", "periods": {}}

    for (year, quarter) in sample_periods:
        period_key = f"{year}_{quarter}"
        period_dir = data_dir / period_key / "parquet"
        if not period_dir.exists():
            continue

        period_info: Dict[str, Any] = {}
        for name in ["sub", "num", "pre", "tag"]:
            path = period_dir / f"{name}.parquet"
            if not path.exists():
                continue
            try:
                n_rows = (
                    pl.scan_parquet(str(path))
                    .select(pl.count())
                    .collect()
                    .item()
                )
                period_info[name] = {"rows": int(n_rows)}
            except Exception as e:
                period_info[name] = {"error": str(e)}
        snapshot["periods"][period_key] = period_info

    return snapshot


def run_all_checks(data_dir: Path | None = None) -> Dict[str, Any]:
    """
    Run the full monitoring suite and return a dictionary summary.

    The result has the shape:
        {
            "periods": { (year, q): {...}, ... },
            "file_validation": [...],
            "fundamentals": {...},
            "integrity": {...},
            "performance": {...},
        }
    """
    data_dir = data_dir or DATA_DIR
    logger.info("Running monitoring checks on data_dir=%s", data_dir)

    checks: Dict[str, Any] = {}

    # 1. Audit available FSN periods and missing parquet files
    try:
        checks["periods"] = audit_available_periods(data_dir)
    except Exception as e:
        logger.exception("Error during audit_available_periods.")
        checks["periods"] = {"error": str(e)}

    # 2. Parquet file validation (can we read them?)
    try:
        checks["file_validation"] = validate_parquet_files(data_dir)
    except Exception as e:
        logger.exception("Error during validate_parquet_files.")
        checks["file_validation"] = {"error": str(e)}

    # 3. Fundamentals structural validation (via Polars engine)
    try:
        checks["fundamentals"] = _compute_fundamentals_check(data_dir)
    except Exception as e:
        logger.exception("Error during fundamentals validation.")
        checks["fundamentals"] = {"status": "ERROR", "error": str(e)}

    # 4. Cross-file integrity (SUB/NUM quality checks)
    try:
        checks["integrity"] = run_integrity_checks(data_dir)
    except Exception as e:
        logger.exception("Error during run_integrity_checks.")
        checks["integrity"] = {"error": str(e)}

    # 5. Basic performance snapshot
    try:
        checks["performance"] = _performance_snapshot(data_dir)
    except Exception as e:
        logger.exception("Error during performance snapshot.")
        checks["performance"] = {"status": "ERROR", "error": str(e)}

    return checks
