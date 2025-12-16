# secfsn/polars_engine.py

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Iterable, Optional, Sequence, Tuple, List

import polars as pl
import pandas as pd

from secfsn.config.core import DATA_DIR
from secfsn.common.logging_utils import get_logger


logger = logging.getLogger("secfsn_polars")

# -------------------------------------------------------------------
# TAG SETS
# -------------------------------------------------------------------

REVENUE_TAGS: List[str] = [
    "Revenues",
    "SalesRevenueNet",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
]

NET_INCOME_TAGS: List[str] = [
    "NetIncomeLoss",
    "ProfitLoss",
]

GROSS_PROFIT_TAGS: List[str] = [
    "GrossProfit",
    "GrossProfitLoss",
]

OPERATING_INCOME_TAGS: List[str] = [
    "OperatingIncomeLoss",
]

EPS_BASIC_TAGS: List[str] = [
    "EarningsPerShareBasic",
]

EPS_DILUTED_TAGS: List[str] = [
    "EarningsPerShareDiluted",
]

ASSETS_TAGS: List[str] = [
    "Assets",
    "AssetsTotal",
]

LIABILITIES_TAGS: List[str] = [
    "Liabilities",
    "LiabilitiesTotal",
]

EQUITY_TAGS: List[str] = [
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "StockholdersEquityAttributableToParent",
    "LiabilitiesAndStockholdersEquity",
    "LiabilitiesAndStockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "LiabilitiesAndStockholdersEquityExcludingPortionAttributableToNoncontrollingInterest",
]

CFO_TAGS: List[str] = [
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
]

CFI_TAGS: List[str] = [
    "NetCashProvidedByUsedInInvestingActivities",
    "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations",
]

CFF_TAGS: List[str] = [
    "NetCashProvidedByUsedInFinancingActivities",
    "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations",
]


# -------------------------------------------------------------------
# INTERNAL HELPERS
# -------------------------------------------------------------------

def _period_dir(year: int, quarter: int, base_dir: Optional[Path]) -> Path:
    """
    Return the parquet directory for (year, quarter).

    If base_dir is provided, use that, otherwise default to
    DATA_DIR / f"{year}_{quarter}" / "parquet".
    """
    root = base_dir or DATA_DIR
    return root / f"{year}_{quarter}" / "parquet"


def _load_sub_num_lazy(
    year: int,
    quarter: int,
    base_dir: Optional[Path] = None,
) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    """
    Lazily load SUB and NUM parquet tables for a given period.

    We normalize:
      - cik -> Int64
      - period -> Int64
    so that downstream Pandas queries like `cik == 320193` work.
    """
    pq_dir = _period_dir(year, quarter, base_dir)
    sub_path = pq_dir / "sub.parquet"
    num_path = pq_dir / "num.parquet"

    logger.info("[START] build_fundamentals_polars %s_%s", year, quarter)

    sub_lazy = (
        pl.scan_parquet(str(sub_path))
        .with_columns(
            pl.col("cik").cast(pl.Int64),
            pl.col("period").cast(pl.Int64),
        )
    )

    num_lazy = pl.scan_parquet(str(num_path))

    return sub_lazy, num_lazy


def _tag_max_expr(tags: Sequence[str]) -> pl.Expr:
    """
    Helper expression: max(value) for rows where tag is in `tags`.

    Implemented without pl.max(...) wrapper to avoid Expr/col() issues
    in newer Polars versions. To be used inside group_by("adsh").agg([...]).
    """
    tag_list = list(tags)
    return (
        pl.when(pl.col("tag").is_in(tag_list))
        .then(pl.col("value").cast(pl.Float64))
        .otherwise(None)
        .max()
    )


# -------------------------------------------------------------------
# CORE POLARS ENGINE (SINGLE PERIOD)
# -------------------------------------------------------------------

def build_fundamentals_polars(
    year: int,
    quarter: int,
    base_dir: Optional[Path] = None,
    forms: Iterable[str] = ("10-K", "10-Q"),
) -> pl.DataFrame:
    """
    Build fundamentals for a single FSN period (year, quarter) using Polars.

    Returns one row per filing (SUB row) enriched with:
      - core fundamental metrics (revenue, net_income, assets, etc.)
      - derived ratios (margins, ROA/ROE, leverage, FCF approximations)
    """
    sub_lazy, num_lazy = _load_sub_num_lazy(year, quarter, base_dir)
    forms_list = list(forms)

    # Filter SUB to forms of interest (10-K / 10-Q)
    sub_filtered = sub_lazy.filter(pl.col("form").is_in(forms_list))

    # Count rows for logging
    sub_count = sub_filtered.select(pl.count()).collect().item()
    logger.info(
        "Filtered SUB to %d filings (forms=%s)",
        sub_count,
        forms_list,
    )

    # Get list of ADSH values to filter NUM
    adsh_list = (
        sub_filtered.select("adsh")
        .unique()
        .collect()
        .get_column("adsh")
        .to_list()
    )

    # Filter NUM to these filings and ensure numeric 'value'
    num_filtered = (
        num_lazy
        .filter(pl.col("adsh").is_in(adsh_list))
        .with_columns(pl.col("value").cast(pl.Float64))
    )

    # Aggregate NUM into one row per ADSH with desired tags
    fundamentals_lazy = num_filtered.group_by("adsh").agg(
        # Income statement
        revenue=_tag_max_expr(REVENUE_TAGS),
        net_income=_tag_max_expr(NET_INCOME_TAGS),
        gross_profit=_tag_max_expr(GROSS_PROFIT_TAGS),
        operating_income=_tag_max_expr(OPERATING_INCOME_TAGS),
        eps_basic=_tag_max_expr(EPS_BASIC_TAGS),
        eps_diluted=_tag_max_expr(EPS_DILUTED_TAGS),
        # Balance sheet
        total_assets=_tag_max_expr(ASSETS_TAGS),
        total_liabilities=_tag_max_expr(LIABILITIES_TAGS),
        total_equity=_tag_max_expr(EQUITY_TAGS),
        # Cash flows
        cfo=_tag_max_expr(CFO_TAGS),
        cfi=_tag_max_expr(CFI_TAGS),
        cff=_tag_max_expr(CFF_TAGS),
    )

    # Join SUB + fundamentals
    joined_lazy = sub_filtered.join(
        fundamentals_lazy,
        on="adsh",
        how="left",
    )

    # Derived metrics
    start = time.perf_counter()
    result = (
        joined_lazy
        .with_columns(
            # Margins
            (pl.col("gross_profit") / pl.col("revenue")).alias("gross_margin"),
            (pl.col("operating_income") / pl.col("revenue")).alias("operating_margin"),
            (pl.col("net_income") / pl.col("revenue")).alias("net_margin"),
            # Balance sheet / profitability ratios
            (pl.col("net_income") / pl.col("total_assets")).alias("roa"),
            (pl.col("net_income") / pl.col("total_equity")).alias("roe"),
            (pl.col("revenue") / pl.col("total_assets")).alias("asset_turnover"),
            (pl.col("total_liabilities") / pl.col("total_equity")).alias("debt_to_equity"),
            (pl.col("total_liabilities") / pl.col("total_assets")).alias("debt_to_assets"),
            (pl.col("total_equity") / pl.col("total_assets")).alias("equity_ratio"),
            (pl.col("total_assets") / pl.col("total_equity")).alias("assets_to_equity"),
            # FCF approximations
            (pl.col("cfo") + pl.col("cfi")).alias("fcf_approx"),
            (pl.col("cfo") + pl.col("cfi")) / pl.col("net_income").alias("fcf_to_net_income"),
        )
        .collect()
    )
    elapsed = time.perf_counter() - start

    logger.info(
        "[END]   build_fundamentals_polars %s_%s (rows=%d, cols=%d, elapsed=%.3fs)",
        year,
        quarter,
        result.height,
        result.width,
        elapsed,
    )

    return result


def build_fundamentals_polars_pandas(
    year: int,
    quarter: int,
    base_dir: Optional[Path] = None,
    forms: Iterable[str] = ("10-K", "10-Q"),
) -> pd.DataFrame:
    """
    Convenience wrapper: same as build_fundamentals_polars, but returns a Pandas DF.
    """

    df_pl = build_fundamentals_polars(
        year=year,
        quarter=quarter,
        base_dir=base_dir,
        forms=forms,
    )

    df = df_pl.to_pandas()

    # ---------------------------------------------------------
    # 🔥 NEW: enforce correct numeric types for all fields
    # ---------------------------------------------------------
    numeric_cols = [
        # public float metadata
        "pubfloatusd", "floataxis", "floatmems",

        # core financials
        "revenue", "net_income", "gross_profit", "operating_income",
        "eps_basic", "eps_diluted",
        "total_assets", "total_liabilities", "total_equity",

        # cash flows
        "cfo", "cfi", "cff",
        "fcf_approx", "fcf_to_net_income",

        # margins
        "gross_margin", "operating_margin", "net_margin",

        # ratios
        "roa", "roe", "asset_turnover",
        "debt_to_equity", "debt_to_assets", "equity_ratio", "assets_to_equity",
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df



# -------------------------------------------------------------------
# MULTI-PERIOD ENGINE (PANEL) + YoY / TTM / Δ
# -------------------------------------------------------------------

def build_fundamentals_polars_multi(
    periods: Sequence[Tuple[int, int]],
    base_dir: Optional[Path] = None,
    forms: Iterable[str] = ("10-K", "10-Q"),
) -> pl.DataFrame:
    """
    Build fundamentals for multiple (year, quarter) periods and concat into a panel.

    Adds dataset_year and dataset_quarter columns to each row.
    """
    if not periods:
        raise ValueError("periods must be a non-empty list of (year, quarter) tuples")

    frames: List[pl.DataFrame] = []
    total_start = time.perf_counter()
    logger.info("[START] build_fundamentals_polars_multi %s", periods)

    for (year, quarter) in periods:
        logger.info("Multi-period: starting %s_%s", year, quarter)
        df = build_fundamentals_polars(
            year=year,
            quarter=quarter,
            base_dir=base_dir,
            forms=forms,
        )

        # Attach dataset period for traceability
        df = df.with_columns(
            pl.lit(year).alias("dataset_year"),
            pl.lit(quarter).alias("dataset_quarter"),
        )
        frames.append(df)

    panel = pl.concat(frames, how="diagonal_relaxed")
    elapsed = time.perf_counter() - total_start
    logger.info(
        "[END]   build_fundamentals_polars_multi %s (rows=%d, cols=%d, elapsed=%.3fs)",
        periods,
        panel.height,
        panel.width,
        elapsed,
    )

    return panel


def _add_yoy_ttm_and_deltas(df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrich panel dataset with:
      - YoY metrics (4-quarter pct_change per CIK)
      - TTM sums and YoY on TTM
      - Period-over-period deltas (diffs)

    Assumes df has:
      - 'cik' column (numeric, Int64)
      - 'period' (int YYYYMMDD) or sortable period key
    """
    df = df.copy()

    # Sort so pct_change/diff/rolling are meaningful
    if "period" in df.columns:
        df = df.sort_values(["cik", "period"])
    else:
        df = df.sort_values(["cik", "dataset_year", "dataset_quarter"])

    g = df.groupby("cik")

    # 1) YoY pct_change for core numeric columns
    yoy_cols = [
        "revenue",
        "net_income",
        "gross_profit",
        "operating_income",
        "eps_basic",
        "eps_diluted",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "cfo",
        "cfi",
        "fcf_approx",
        # margins / ratios
        "gross_margin",
        "operating_margin",
        "net_margin",
        "roa",
        "roe",
        "asset_turnover",
        "debt_to_equity",
        "debt_to_assets",
        "equity_ratio",
        "assets_to_equity",
        "fcf_to_net_income",
    ]

    for col in yoy_cols:
        if col in df.columns:
            df[f"{col}_yoy"] = g[col].pct_change(periods=4, fill_method=None)

    # 2) TTM metrics via rolling 4-quarter sums
    ttm_sum_cols = [
        "revenue",
        "net_income",
        "gross_profit",
        "operating_income",
        "fcf_approx",
    ]

    for col in ttm_sum_cols:
        if col in df.columns:
            df[f"ttm_{col}"] = (
                g[col]
                .rolling(window=4, min_periods=1)
                .sum()
                .reset_index(level=0, drop=True)
            )

    # TTM margins (simple: TTM net income / TTM revenue)
    if "ttm_net_income" in df.columns and "ttm_revenue" in df.columns:
        df["ttm_net_margin"] = df["ttm_net_income"] / df["ttm_revenue"]

    # 3) YoY on TTM metrics
    if "ttm_revenue" in df.columns:
        df["ttm_revenue_yoy"] = g["ttm_revenue"].pct_change(periods=4, fill_method=None)

    if "ttm_net_income" in df.columns:
        df["ttm_net_income_yoy"] = g["ttm_net_income"].pct_change(periods=4, fill_method=None)

    if "ttm_net_margin" in df.columns:
        df["ttm_net_margin_yoy"] = g["ttm_net_margin"].pct_change(periods=4, fill_method=None)

    if "ttm_fcf_approx" in df.columns:
        df["ttm_fcf_approx_yoy"] = g["ttm_fcf_approx"].pct_change(periods=4, fill_method=None)

    # 4) Period-over-period deltas (absolute change)
    delta_cols = [
        "revenue",
        "net_income",
        "gross_profit",
        "operating_income",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "roa",
        "roe",
        "asset_turnover",
        "debt_to_equity",
        "debt_to_assets",
        "equity_ratio",
        "assets_to_equity",
        "fcf_approx",
        "fcf_to_net_income",
    ]

    for col in delta_cols:
        if col in df.columns:
            df[f"{col}_delta"] = g[col].diff()

    return df


def build_fundamentals_polars_multi_pandas(
    periods: Sequence[Tuple[int, int]],
    base_dir: Optional[Path] = None,
    forms: Iterable[str] = ("10-K", "10-Q"),
) -> pd.DataFrame:
    """
    Multi-period fundamentals, returned as a Pandas DataFrame,
    enriched with YoY / TTM / Δ fields.

    This is the function you'll typically call from notebooks:

        df_panel = build_fundamentals_polars_multi_pandas(
            periods=[(2024, 3), (2024, 4)],
            base_dir=Path("C:/Users/JR/OneDrive/Mini PC/secfsn/data"),
        )

    Columns added (examples):
        - revenue_yoy, net_income_yoy, net_margin_yoy
        - ttm_revenue, ttm_net_income, ttm_net_margin
        - ttm_revenue_yoy, ttm_net_income_yoy, ttm_net_margin_yoy
        - revenue_delta, net_margin_delta, roa_delta, ...
    """
    df_pl = build_fundamentals_polars_multi(
        periods=periods,
        base_dir=base_dir,
        forms=forms,
    )
    df = df_pl.to_pandas()
    df = _add_yoy_ttm_and_deltas(df)
    return df
