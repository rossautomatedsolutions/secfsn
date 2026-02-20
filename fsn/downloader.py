import time
from pathlib import Path
from typing import Iterable, Tuple, List
from io import BytesIO
from zipfile import ZipFile, BadZipFile

import requests


from secfsn.config.core import DATA_DIR
from secfsn.config.constants import (
    FSN_BASE_URL,
    FSN_USER_AGENT,
    FSN_QUARTERS,
    FSN_MONTHS,
)
from secfsn.common.logging_utils import get_logger
from secfsn.common.timing import timed


logger = get_logger("fsn_downloader")


def _quarter_period_folder(year: int, quarter: int) -> Path:
    """
    Return quarterly period folder like DATA_DIR / '2022_1'.
    """
    return DATA_DIR / f"{year}_{quarter}"


def _month_period_folder(year: int, month: int) -> Path:
    """
    Return monthly period folder like DATA_DIR / '2024_01'.

    Zero-padding avoids collisions with quarterly folders (e.g. '2024_4').
    """
    return DATA_DIR / f"{year}_{month:02d}"


def _validate_period_pairs(periods: Iterable[Tuple[int, int]], kind: str) -> list[Tuple[int, int]]:
    validated: list[Tuple[int, int]] = []
    for idx, item in enumerate(periods):
        if not isinstance(item, tuple) or len(item) != 2:
            raise ValueError(
                f"Invalid {kind} entry at index {idx}: {item!r}. "
                "Expected (year, period) tuples."
            )
        y, p = item
        if not isinstance(y, int) or not isinstance(p, int):
            raise ValueError(f"Invalid {kind} tuple at index {idx}: {item!r}. Expected ints.")
        validated.append((y, p))
    return validated


def _quarter_zip_name(year: int, quarter: int) -> str:
    """
    Quarterly naming: 2022q1_notes.zip
    """
    return f"{year}q{quarter}_notes.zip"


def _month_zip_name(year: int, month: int) -> str:
    """
    Monthly naming: 2024_10_notes.zip
    """
    return f"{year}_{month:02d}_notes.zip"


def _fsn_zip_url(file_name: str) -> str:
    return f"{FSN_BASE_URL}/{file_name}"


@timed("download_and_extract_quarter", logger_name="fsn_downloader")
def download_and_extract_quarter(year: int, quarter: int, overwrite: bool = False) -> Path:
    """
    Download and extract a quarterly FSN zip into:
        DATA_DIR / f'{year}_{quarter}' / 'source'
    """
    period_dir = _quarter_period_folder(year, quarter)
    source_dir = period_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite and any(source_dir.glob("*")):
        logger.info(f"Source already populated for quarter {year}q{quarter}, skipping download.")
        return period_dir

    file_name = _quarter_zip_name(year, quarter)
    url = _fsn_zip_url(file_name)

    headers = {"User-Agent": FSN_USER_AGENT}
    logger.info(f"Downloading quarterly FSN ZIP {file_name} from {url}")
    resp = requests.get(url, headers=headers, timeout=90)
    resp.raise_for_status()

    try:
        with ZipFile(BytesIO(resp.content)) as zf:
            for member in zf.namelist():
                out_path = source_dir / member
                if out_path.exists() and not overwrite:
                    continue
                logger.info(f"Writing file {member} to {out_path}")
                with out_path.open("wb") as f:
                    f.write(zf.read(member))
    except BadZipFile as e:
        logger.error(f"Bad zip file for {year}q{quarter}: {e}")
        raise

    return period_dir


@timed("download_and_extract_month", logger_name="fsn_downloader")
def download_and_extract_month(year: int, month: int, overwrite: bool = False) -> Path:
    """
    Download and extract a monthly FSN zip into:
        DATA_DIR / f'{year}_{month:02d}' / 'source'
    """
    period_dir = _month_period_folder(year, month)
    source_dir = period_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite and any(source_dir.glob("*")):
        logger.info(f"Source already populated for month {year}_{month}, skipping download.")
        return period_dir

    file_name = _month_zip_name(year, month)
    url = _fsn_zip_url(file_name)

    headers = {"User-Agent": FSN_USER_AGENT}
    logger.info(f"Downloading monthly FSN ZIP {file_name} from {url}")
    resp = requests.get(url, headers=headers, timeout=90)
    resp.raise_for_status()

    try:
        with ZipFile(BytesIO(resp.content)) as zf:
            for member in zf.namelist():
                out_path = source_dir / member
                if out_path.exists() and not overwrite:
                    continue
                logger.info(f"Writing file {member} to {out_path}")
                with out_path.open("wb") as f:
                    f.write(zf.read(member))
    except BadZipFile as e:
        logger.error(f"Bad zip file for {year}_{month}: {e}")
        raise

    return period_dir


@timed("download_and_extract_all_fsn", logger_name="fsn_downloader")
def download_and_extract_all_fsn(
    quarters: Iterable[Tuple[int, int]] | None = None,
    months: Iterable[Tuple[int, int]] | None = None,
    overwrite: bool = False,
) -> List[Path]:
    """
    Download and extract all configured quarterly + monthly FSN zips.

    Returns a list of period directories (DATA_DIR / 'YYYY_P').
    """
    quarters = _validate_period_pairs(quarters or FSN_QUARTERS, kind="quarter")
    months = _validate_period_pairs(months or FSN_MONTHS, kind="month")

    period_dirs: List[Path] = []

    # Quarterly
    for (y, q) in quarters:
        try:
            pd_dir = download_and_extract_quarter(y, q, overwrite=overwrite)
            period_dirs.append(pd_dir)
        except Exception:
            logger.warning(f"Skipping quarter {y}q{q} due to error.", exc_info=True)

    # Monthly
    for (y, m) in months:
        try:
            pd_dir = download_and_extract_month(y, m, overwrite=overwrite)
            period_dirs.append(pd_dir)
        except Exception:
            logger.warning(f"Skipping month {y}_{m} due to error.", exc_info=True)

    return period_dirs
