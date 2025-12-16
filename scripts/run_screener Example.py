# run_screener Example
"""
Auto Fundamentals Screener
--------------------------

This script:

1. Reads FSN data state from logs/fsn_last_processed.json
2. Reads screener state from logs/screener_last_run.json
3. If FSN has a newer month than the last screener run:
   - Derives the quarter for that month
   - Loads fundamentals via build_fundamentals_polars_pandas
   - Applies a mild fundamental filter
   - Saves results to logs/fundamentals_screener_YYYY_MM.csv
   - Updates screener_last_run.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------
# Path resolution to import secfsn
# ---------------------------------------------------------------------
THIS_FILE = Path(__file__).resolve()
SECFSN_DIR = THIS_FILE.parents[1]
REPO_ROOT = SECFSN_DIR.parent

for p in (SECFSN_DIR, REPO_ROOT):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)

print("=================================================")
print("        FSN FUNDAMENTALS SCREENER (AUTO)")
print("=================================================")

from secfsn.config.core import DATA_DIR
from secfsn.engine.polars_engine import build_fundamentals_polars_pandas

LOGS_DIR = SECFSN_DIR / "logs"
FSN_STATE_FILE = LOGS_DIR / "fsn_last_processed.json"
SCREENER_STATE_FILE = LOGS_DIR / "screener_last_run.json"

# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def load_month_state(path: Path) -> Optional[Tuple[int, int]]:
    if not path.exists():
        return None
    try:
        data = json.load(path.open("r", encoding="utf-8"))
        return int(data["year"]), int(data["month"])
    except:
        return None


def save_month_state(path: Path, year: int, month: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump({"year": year, "month": month}, f, indent=2)
    print(f"[STATE] Updated {path.name} → {year}-{month:02d}")


def month_to_quarter(month: int) -> int:
    return (month - 1) // 3 + 1


# ---------------------------------------------------------------------
# Screener logic
# ---------------------------------------------------------------------
def run_full_fundamentals_screener(df: pd.DataFrame) -> pd.DataFrame:
    """
    Very mild screener:
    - requires revenue >= 0
    - sorts by revenue descending
    """
    if "revenue" not in df.columns:
        return df.iloc[0:0].copy()

    mask = df["revenue"].notna() & (df["revenue"] >= 0)
    results = df[mask].copy()

    if "revenue" in results.columns:
        results = results.sort_values("revenue", ascending=False)

    return results


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main() -> None:
    print(f"DATA_DIR: {DATA_DIR}\n")

    fsn_state = load_month_state(FSN_STATE_FILE)
    if fsn_state is None:
        print("❌ FSN state missing. Cannot run screener.")
        return

    fsn_year, fsn_month = fsn_state
    print(f"[FSN] Last processed = {fsn_year}-{fsn_month:02d}")

    scr_state = load_month_state(SCREENER_STATE_FILE)
    if scr_state:
        scr_year, scr_month = scr_state
        print(f"[SCREENER] Last run = {scr_year}-{scr_month:02d}")
    else:
        scr_year, scr_month = 0, 0
        print("[SCREENER] No prior run found.")

    # Already up-to-date?
    if (scr_year, scr_month) >= (fsn_year, fsn_month):
        print("✔ Screener is already up-to-date.")
        return

    # Determine target quarter
    qtr = month_to_quarter(fsn_month)
    print(f"[PLAN] Screening fundamentals for {fsn_year} Q{qtr}\n")

    # Load fundamentals
    print("Loading fundamentals...")
    df = build_fundamentals_polars_pandas(
        year=fsn_year,
        quarter=qtr,
        base_dir=DATA_DIR,
    )
    print("Loaded fundamentals:", df.shape, "\n")

    # Run screener
    print("Running full fundamentals screener...")
    results = run_full_fundamentals_screener(df)

    print("-------------------------------------------------")
    print(f"Screener rows: {len(results)}")
    print("-------------------------------------------------")
    if len(results) > 0:
        print(results.head(), "\n")

    # Output
    LOGS_DIR.mkdir(exist_ok=True)
    out_path = LOGS_DIR / f"fundamentals_screener_{fsn_year}_{fsn_month:02d}.csv"
    results.to_csv(out_path, index=False)
    print(f"[OUTPUT] Saved to: {out_path}")

    # Update state
    save_month_state(SCREENER_STATE_FILE, fsn_year, fsn_month)


if __name__ == "__main__":
    main()
