"""
Engine layer for secfsn:

- FSNDataLoader: low level parquet loader
- Polars-based fundamentals: build_fundamentals_polars*
- run_simple_screener: basic fundamentals screener

This is the minimal v0.1 engine, designed to be extended later.
"""

from secfsn.engine.loader import FSNDataLoader, period_key, period_str
from secfsn.engine.screener import run_simple_screener

# Polars fundamentals engine
from secfsn.engine.polars_engine import (
    build_fundamentals_polars,
    build_fundamentals_polars_pandas,
    build_fundamentals_polars_multi,
    build_fundamentals_polars_multi_pandas,
)

__all__ = [
    "FSNDataLoader",
    "run_simple_screener",
    "period_key",
    "period_str",
    "build_fundamentals_polars",
    "build_fundamentals_polars_pandas",
    "build_fundamentals_polars_multi",
    "build_fundamentals_polars_multi_pandas",
]
