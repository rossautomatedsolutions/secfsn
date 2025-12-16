"""
Vectorized FSN Screener
=======================

Loads SUB + NUM for a single (year, quarter) pair and returns raw DataFrames.
This module keeps loading fast and simple so later layers can run fully
vectorized on top of the returned dfs.
"""

import pandas as pd
from pathlib import Path

from secfsn.config.core import DATA_DIR
from secfsn.common.logging_utils import get_logger
from secfsn.engine.loader import FSNDataLoader


logger = get_logger("secfsn_screener")


# ======================================================
#  LOADERS
# ======================================================
def load_sub(year: int, quarter: int, base_dir: Path) -> pd.DataFrame:
    """
    Load sub.parquet for a specific (year, quarter).
    """
    period = f"{year}_{quarter}"
    path = base_dir / period / "parquet" / "sub.parquet"
    logger.info(f"Loading SUB from {path}")

    if not path.exists():
        raise FileNotFoundError(f"Missing SUB file: {path}")

    df = pd.read_parquet(path)
    return df


def load_num(year: int, quarter: int, base_dir: Path) -> pd.DataFrame:
    """
    Load num.parquet for a specific (year, quarter).
    """
    period = f"{year}_{quarter}"
    path = base_dir / period / "parquet" / "num.parquet"
    logger.info(f"Loading NUM from {path}")

    if not path.exists():
        raise FileNotFoundError(f"Missing NUM file: {path}")

    df = pd.read_parquet(path)
    return df


def load_sub_num(year: int, quarter: int, base_dir: Path):
    """
    Convenience helper: load both SUB + NUM.
    """
    sub = load_sub(year, quarter, base_dir=base_dir)
    num = load_num(year, quarter, base_dir=base_dir)

    logger.info(f"SUB: {sub.shape}, NUM: {num.shape}")
    return sub, num


# ======================================================
#  SIMPLE SCREENER (BASELINE)
# ======================================================

def simple_merge(sub: pd.DataFrame, num: pd.DataFrame) -> pd.DataFrame:
    """
    Joins SUB + key NUM facts into a wide table.
    This keeps minimal mapping. Later layers add metrics.
    """

    # Filter only 10-K / 10-Q
    filings = sub[sub["form"].isin(["10-K", "10-Q"])].copy()

    # Key tags to pull from NUM
    key_tags = {
        "revenue": "Revenues",
        "net_income": "NetIncomeLoss",
        "gross_profit": "GrossProfit",
        "operating_income": "OperatingIncomeLoss",
        "eps_basic": "EarningsPerShareBasic",
        "eps_diluted": "EarningsPerShareDiluted",
        "total_assets": "Assets",
        "total_liabilities": "Liabilities",
        "total_equity": "StockholdersEquity",
    }

    out = filings[["cik", "name", "adsh", "form", "fy", "fp", "period", "filed"]].copy()

    # Extract each tag
    for col, tag in key_tags.items():
        tag_df = num[num["tag"] == tag][["adsh", "value"]].rename(columns={"value": col})
        out = out.merge(tag_df, on="adsh", how="left")

    # Basic margins
    out["gross_margin"] = out["gross_profit"] / out["revenue"]
    out["operating_margin"] = out["operating_income"] / out["revenue"]
    out["net_margin"] = out["net_income"] / out["revenue"]

    return out


def run_simple_screener(
    year: int,
    quarter: int,
    base_dir: Path,
    min_revenue: float = None,
    min_net_margin: float = None,
    output_csv: Path = None,
    output_json: Path = None,
    max_companies: int = None,
):
    """
    Wrapper that:
      1. loads SUB + NUM
      2. builds wide screener table
      3. applies minimal filters
    """

    with logger.context(f"Simple screener for {year}_{quarter}"):
        sub, num = load_sub_num(year, quarter, base_dir=base_dir)

        df = simple_merge(sub, num)

        # Apply filters
        if min_revenue is not None:
            df = df[df["revenue"] >= min_revenue]

        if min_net_margin is not None:
            df = df[df["net_margin"] >= min_net_margin]

        if max_companies:
            df = df.head(max_companies)

        # Save
        if output_csv:
            output_csv.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(output_csv, index=False)
            logger.info(f"Wrote screener CSV to {output_csv}")

        if output_json:
            output_json.parent.mkdir(parents=True, exist_ok=True)
            df.to_json(output_json, orient="records")
            logger.info(f"Wrote screener JSON to {output_json}")

        return df
