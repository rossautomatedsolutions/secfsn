from pathlib import Path
from typing import Iterable

import pandas as pd

from secfsn.config.core import DATA_DIR
from secfsn.config.constants import TSV_TABLES, INCLUDE_TXT_TABLE
from secfsn.common.logging_utils import get_logger
from secfsn.common.timing import timed

logger = get_logger("fsn_tsv_to_parquet")


def _find_period_dirs(base_dir: Path) -> Iterable[Path]:
    """
    Yield all subdirectories under base_dir that contain a 'source' folder.
    """
    for child in base_dir.iterdir():
        if child.is_dir() and (child / "source").exists():
            yield child


@timed("convert_period_tsv_to_parquet", logger_name="fsn_tsv_to_parquet")
def convert_period_tsv_to_parquet(period_dir: Path):
    """
    Convert all TSV files in:
        period_dir / 'source'/*.tsv
    into:
        period_dir / 'parquet'/*.parquet

    Then delete TSV files and the 'source' folder.
    """
    source_dir = period_dir / "source"
    parquet_dir = period_dir / "parquet"
    parquet_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"Converting TSVs for period: {period_dir.name}")

    for table in TSV_TABLES:
        tsv_path = source_dir / f"{table}.tsv"
        if not tsv_path.exists():
            continue

        if table == "txt" and not INCLUDE_TXT_TABLE:
            logger.info(f"Skipping txt.tsv for period {period_dir.name} (disabled).")
            try:
                tsv_path.unlink()
            except OSError:
                pass
            continue

        parquet_path = parquet_dir / f"{table}.parquet"

        try:
            logger.info(f"Reading TSV: {tsv_path}")
            df = pd.read_csv(
                tsv_path,
                sep="\t",
                encoding="latin1",
                low_memory=False,
                on_bad_lines="warn",
                dtype=str,
            )
            logger.info(f"Writing parquet: {parquet_path}")
            df.to_parquet(parquet_path, index=False)
        except Exception as e:
            logger.warning(f"Error converting {tsv_path} to parquet: {e}")
            continue
        finally:
            # Delete TSV in all cases to reclaim space
            try:
                tsv_path.unlink()
            except OSError:
                pass

    # Attempt to remove any leftovers and delete source folder
    try:
        for leftover in source_dir.iterdir():
            leftover.unlink()
        source_dir.rmdir()
        logger.info(f"Deleted source folder for period {period_dir.name}")
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning(f"Could not fully delete source folder {source_dir}: {e}")


@timed("convert_all_tsv_to_parquet", logger_name="fsn_tsv_to_parquet")
def convert_all_tsv_to_parquet(base_dir: Path | None = None):
    """
    Convert TSVs to parquet for every period that has a 'source' folder
    under base_dir (default: DATA_DIR).
    """
    base = base_dir or DATA_DIR
    for period_dir in _find_period_dirs(base):
        convert_period_tsv_to_parquet(period_dir)
