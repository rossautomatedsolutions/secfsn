from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

from secfsn.config.core import DATA_DIR
from secfsn.fsn.downloader import download_and_extract_month, _month_period_folder
from secfsn.fsn.tsv_to_parquet import convert_period_tsv_to_parquet
from secfsn.fsn.quarter_combiner import combine_months_into_quarters

LOGS_DIR = Path(__file__).resolve().parents[1] / "logs"
STATE_FILE = LOGS_DIR / "fsn_last_processed.json"
REQUIRED_TABLES = ("sub", "num", "pre", "tag")


@dataclass(frozen=True, order=True)
class MonthKey:
    year: int
    month: int


def _load_state(path: Path) -> MonthKey | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return MonthKey(int(payload["year"]), int(payload["month"]))
    except Exception:
        return None


def _save_state(path: Path, key: MonthKey) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"year": key.year, "month": key.month}, indent=2), encoding="utf-8")


def _next_month(key: MonthKey) -> MonthKey:
    if key.month == 12:
        return MonthKey(key.year + 1, 1)
    return MonthKey(key.year, key.month + 1)


def _candidate_month(last: MonthKey | None, today: date | None = None) -> MonthKey:
    if last is not None:
        return _next_month(last)
    d = today or date.today()
    if d.month == 1:
        return MonthKey(d.year - 1, 12)
    return MonthKey(d.year, d.month - 1)


def _quarter(month: int) -> int:
    return ((month - 1) // 3) + 1


def _has_complete_parquet(period_dir: Path, tables: Iterable[str] = REQUIRED_TABLES) -> bool:
    parquet_dir = period_dir / "parquet"
    if not parquet_dir.exists():
        return False
    for table in tables:
        table_path = parquet_dir / f"{table}.parquet"
        if not table_path.exists() or table_path.stat().st_size == 0:
            return False
    return True


def _canonical_month_dir(year: int, month: int) -> Path:
    return _month_period_folder(year, month)


def _canonical_quarter_dir(year: int, quarter: int) -> Path:
    # Canonical quarter folder naming across pipeline/engine is YYYY_QNUM (example: 2026_1).
    return DATA_DIR / f"{year}_{quarter}"


def _legacy_q_prefixed_quarter_dir(year: int, quarter: int) -> Path:
    # Non-canonical legacy variant (example: 2026_Q1).
    return DATA_DIR / f"{year}_Q{quarter}"


def run_daily_update() -> bool:
    """
    Returns True only when state was advanced.

    Advancement guardrails:
    1) Candidate month source is downloaded/extracted.
    2) Candidate month canonical folder YYYY_MM has non-empty required parquet tables.
    3) Candidate quarter folder YYYY_Q has non-empty required parquet tables after combine.
    """
    last = _load_state(STATE_FILE)
    candidate = _candidate_month(last)

    qnum = _quarter(candidate.month)
    month_dir = _canonical_month_dir(candidate.year, candidate.month)
    quarter_dir = _canonical_quarter_dir(candidate.year, qnum)
    legacy_q_dir = _legacy_q_prefixed_quarter_dir(candidate.year, qnum)

    legacy_fallback_used = False
    print(
        "[DIAGNOSTIC] "
        f"month_dir={month_dir} exists={month_dir.exists()} | "
        f"quarter_dir={quarter_dir} exists={quarter_dir.exists()} | "
        f"legacy_quarter_dir={legacy_q_dir} exists={legacy_q_dir.exists()} | "
        f"legacy_fallback_used={legacy_fallback_used}"
    )

    # 1) Download/extract candidate month (idempotent if source already exists)
    download_and_extract_month(candidate.year, candidate.month, overwrite=False)

    # 2) Convert candidate month TSV -> parquet and verify canonical monthly output
    convert_period_tsv_to_parquet(month_dir)
    if not _has_complete_parquet(month_dir):
        return False

    # 3) Combine candidate month into quarter and verify downstream quarter parquet usability
    combine_months_into_quarters(
        months=[(candidate.year, candidate.month)],
        base_dir=DATA_DIR,
        delete_month_periods=False,
    )

    if not _has_complete_parquet(quarter_dir):
        return False

    _save_state(STATE_FILE, candidate)
    return True


if __name__ == "__main__":
    updated = run_daily_update()
    print("advanced" if updated else "not_advanced")
