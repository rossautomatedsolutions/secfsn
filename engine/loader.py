from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from pathlib import Path
import pandas as pd

from secfsn.config.core import DATA_DIR
from secfsn.common.logging_utils import get_logger
from secfsn.common.timing import log_timing


logger = get_logger("fsn_loader")

Period = Tuple[int, int]  # (year, quarter)


def period_str(year: int, quarter: int) -> str:
    """Return canonical period string like '2022_1' or '2024_4'."""
    return f"{year}_{quarter}"


def period_key(period: Period | str) -> str:
    """Normalize period identifiers (either tuple or string) to 'YYYY_Q' string."""
    if isinstance(period, str):
        return period
    y, q = period
    return period_str(y, q)


def get_period_dir(period: Period | str, base_dir: Path | None = None) -> Path:
    """Return the directory containing parquet for a given FSN period."""
    base = base_dir or DATA_DIR
    return base / period_key(period)


@dataclass
class FSNDataLoader:
    """
    Low-level loader for FSN parquet tables.

    - Handles locating 'parquet/' subdirectories under each period folder
    - Lazily loads tables and caches them in memory by period
    - Designed to be shared by higher-level engines (fundamentals, screener)
    """

    periods: List[Period]
    base_dir: Path = DATA_DIR

    def __post_init__(self) -> None:
        # normalize periods into canonical string keys
        self._period_keys: List[str] = [period_key(p) for p in self.periods]
        # cache: { (period_key, table_name) -> DataFrame }
        self._cache: Dict[Tuple[str, str], pd.DataFrame] = {}

    @classmethod
    def for_single_period(cls, year: int, quarter: int, base_dir: Path | None = None) -> "FSNDataLoader":
        """Convenience constructor for a single quarter."""
        return cls(periods=[(year, quarter)], base_dir=base_dir or DATA_DIR)

    def _parquet_path(self, period: str, table: str) -> Path:
        """Return the path to a specific parquet table for a period."""
        period_dir = get_period_dir(period, self.base_dir)
        parquet_dir = period_dir / "parquet"
        return parquet_dir / f"{table}.parquet"

    def load_table(self, table: str, period: Period | str) -> pd.DataFrame:
        """
        Load a specific FSN table (e.g., 'sub', 'num') for the given period.

        Results are cached so repeated access is fast.
        """
        key = period_key(period)
        cache_key = (key, table)

        if cache_key in self._cache:
            return self._cache[cache_key]

        path = self._parquet_path(key, table)
        if not path.exists():
            raise FileNotFoundError(f"Parquet file not found: {path}")

        with log_timing(f"load_table {table} for {key}", logger_name="fsn_loader"):
            df = pd.read_parquet(path)

        self._cache[cache_key] = df
        logger.info(f"Loaded table '{table}' for period {key} with {len(df):,} rows.")
        return df

    # Convenience accessors -------------------------------------------------

    def load_sub(self, period: Period | str) -> pd.DataFrame:
        return self.load_table("sub", period)

    def load_num(self, period: Period | str) -> pd.DataFrame:
        return self.load_table("num", period)

    def available_periods(self) -> Iterable[str]:
        """Return the list of period keys known to this loader."""
        return list(self._period_keys)

    def load_pre(self, period: Period | str) -> pd.DataFrame:
        return self.load_table("pre", period)

    def load_tag(self, period: Period | str) -> pd.DataFrame:
        return self.load_table("tag", period)

    def load_txt(self, period: Period | str) -> pd.DataFrame:
        return self.load_table("txt", period)

    def load_all(self, period: Period | str):
        """Return (sub, num, pre, tag, txt) as a tuple."""
        return (
            self.load_sub(period),
            self.load_num(period),
            self.load_pre(period),
            self.load_tag(period),
            self.load_txt(period),
        )

    def load_period(self, year: int, quarter: int):
        return self.load_all((year, quarter))
