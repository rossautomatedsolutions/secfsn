from pathlib import Path
from typing import Iterable, Tuple
import shutil
import pandas as pd

from secfsn.config.core import DATA_DIR
from secfsn.config.constants import TSV_TABLES
from secfsn.common.logging_utils import get_logger
from secfsn.common.timing import timed



logger = get_logger("fsn_quarter_combiner")


def _quarter_from_month(month: int) -> int:
    """
    Map month 1..12 -> quarter 1..4.
    """
    return (month - 1) // 3 + 1


@timed("combine_months_into_quarters", logger_name="fsn_quarter_combiner")
def combine_months_into_quarters(
    months: Iterable[Tuple[int, int]],
    base_dir: Path | None = None,
    delete_month_periods: bool = True,
):
    """
    Combine monthly period parquet folders into quarterly folders.

    Example:
        months = [(2024, 10), (2024, 11), (2024, 12)]
        -> combined into DATA_DIR / '2024_4' / 'parquet'

    Quarterly FSN periods (e.g. 2022_1) are NOT modified here.
    """
    base = base_dir or DATA_DIR

    # Build mapping: (year, quarter) -> list of monthly period dirs
    quarter_to_month_dirs: dict[tuple[int, int], list[Path]] = {}

    for (year, month) in months:
        q = _quarter_from_month(month)
        period_dir = base / f"{year}_{month}"
        if not period_dir.exists():
            logger.info(f"Monthly period dir not found, skipping: {period_dir}")
            continue
        quarter_to_month_dirs.setdefault((year, q), []).append(period_dir)

    # Now combine each quarter
    for (year, q), month_dirs in quarter_to_month_dirs.items():
        if not month_dirs:
            continue

        quarter_dir = base / f"{year}_{q}"
        quarter_parquet_dir = quarter_dir / "parquet"
        quarter_parquet_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"[START] Combining months {', '.join(md.name for md in month_dirs)} "
            f"into quarter folder {quarter_dir.name}"
        )

        # Combine each table (except txt, which is optional and very large)
        for table in TSV_TABLES:
            if table == "txt":
                continue

            dfs = []
            for mdir in month_dirs:
                parquet_path = mdir / "parquet" / f"{table}.parquet"
                if parquet_path.exists():
                    try:
                        df = pd.read_parquet(parquet_path)
                        dfs.append(df)
                    except Exception as e:
                        logger.warning(f"Failed to read {parquet_path}: {e}")

            if not dfs:
                continue

            combined = pd.concat(dfs, ignore_index=True).drop_duplicates()

            out_path = quarter_parquet_dir / f"{table}.parquet"
            logger.info(f"Writing quarterly parquet table: {out_path}")
            combined.to_parquet(out_path, index=False)

        # Copy notes-metadata.json from first month that has it
        copied_metadata = False
        for mdir in month_dirs:
            meta_path = mdir / "notes-metadata.json"
            if meta_path.exists():
                dest_meta = quarter_dir / "notes-metadata.json"
                logger.info(f"Copying metadata from {meta_path} to {dest_meta}")
                shutil.copy2(meta_path, dest_meta)
                copied_metadata = True
                break
        if not copied_metadata:
            logger.info(f"No metadata JSON found for quarter {year}_{q}")

        # Optionally delete monthly period dirs
        if delete_month_periods:
            for mdir in month_dirs:
                try:
                    # delete parquet contents
                    pdir = mdir / "parquet"
                    if pdir.exists():
                        for f in pdir.iterdir():
                            f.unlink()
                        pdir.rmdir()
                    # delete any remaining metadata/readme
                    for f in mdir.iterdir():
                        try:
                            f.unlink()
                        except IsADirectoryError:
                            pass
                    mdir.rmdir()
                    logger.info(f"Deleted monthly period directory: {mdir}")
                except Exception as e:
                    logger.warning(f"Could not fully delete monthly dir {mdir}: {e}")

        logger.info(f"[END] Combined months into quarter {quarter_dir.name}")
