from pathlib import Path

def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def period_to_str(year: int, period: int) -> str:
    """Quarterly or monthly folder naming (e.g., 2024_10 or 2022_1)."""
    return f"{year}_{period}"
