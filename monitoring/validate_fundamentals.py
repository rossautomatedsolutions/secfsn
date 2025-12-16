"""
validate_fundamentals.py
Check that fundamentals datasets have required columns and no obvious corruption.
"""

from __future__ import annotations

from typing import List

import pandas as pd


REQUIRED_COLS = [
    "cik",
    "period",
    "form",
    "revenue",
    "net_income",
    "ttm_revenue",
    "ttm_net_income",
]


def validate_fundamentals_dataset(df: pd.DataFrame) -> List[str]:
    """
    Basic structural validation of a fundamentals DataFrame.

    Assumptions:
        - df comes from build_fundamentals_polars_multi_pandas(...)
        - One row per filing (cik + adsh)
    """
    errors: List[str] = []

    # 1. Required columns
    missing_cols = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing_cols:
        errors.append(f"Missing required columns: {missing_cols}")

    # 2. CIK must be present
    if "cik" in df.columns and df["cik"].isna().any():
        errors.append("Some rows contain null CIK.")

    # 3. Revenue sanity check
    if "revenue" in df.columns and (df["revenue"] < 0).any():
        errors.append("Negative revenue detected — unusual, check source.")

    return errors
