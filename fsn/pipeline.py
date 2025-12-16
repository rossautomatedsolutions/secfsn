from pathlib import Path

from secfsn.config.core import DATA_DIR
from secfsn.config.constants import FSN_QUARTERS, FSN_MONTHS
from secfsn.common.logging_utils import get_logger
from secfsn.common.timing import log_timing

from secfsn.fsn.downloader import download_and_extract_quarter
from secfsn.fsn.downloader import download_and_extract_month
from secfsn.fsn.downloader import download_and_extract_all_fsn
from secfsn.fsn.tsv_to_parquet import convert_all_tsv_to_parquet
from secfsn.fsn.quarter_combiner import combine_months_into_quarters

logger = get_logger("fsn_pipeline")


def run_fsn_pipeline(
    quarters: list[tuple[int, int]] | None = None,
    months: list[tuple[int, int]] | None = None,
    base_dir: Path | None = None,
    overwrite_source: bool = False,
):
    """
    Full FSN pipeline:

    1) Download + extract quarterly and monthly FSN ZIPs
    2) Convert all TSVs → parquet, delete TSVs + 'source/' folders
    3) Combine monthly parquets into quarterly folders (e.g. 2024_4)
       and delete the monthly period directories.
    """
    quarters = quarters or FSN_QUARTERS
    months = months or FSN_MONTHS
    base = base_dir or DATA_DIR

    # ASCII-only label
    label = "FSN pipeline (download + extract + tsv_to_parquet + monthly_to_quarter)"

    with log_timing(label, logger_name="fsn_pipeline"):
        # Step 1: Download + extract
        period_dirs = download_and_extract_all_fsn(
            quarters=quarters,
            months=months,
            overwrite=overwrite_source,
        )
        logger.info(f"Extracted FSN periods: {[p.name for p in period_dirs]}")

        # Step 2: TSV → parquet (delete TSVs + source dir)
        convert_all_tsv_to_parquet(base_dir=base)

        # Step 3: Combine monthly into quarter folders
        combine_months_into_quarters(
            months=months,
            base_dir=base,
            delete_month_periods=True
        )


if __name__ == "__main__":
    run_fsn_pipeline()
