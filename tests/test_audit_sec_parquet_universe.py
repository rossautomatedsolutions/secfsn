from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_sec_parquet_universe.py"
SPEC = importlib.util.spec_from_file_location("audit_sec_parquet_universe", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
audit_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = audit_module
SPEC.loader.exec_module(audit_module)


def _write_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


def test_handles_missing_sub_parquet(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    period_dir = data_root / "2025_1" / "parquet"
    period_dir.mkdir(parents=True)
    _write_parquet(pd.DataFrame({"adsh": ["a1"], "value": [1.0]}), period_dir / "num.parquet")

    audit = audit_module.audit_quarter("2025_1", data_root / "2025_1", data_root)

    assert audit.sub_exists is False
    assert audit.num_exists is True
    assert audit.known_large_cap_classification["Apple"] == "absent_from_sub"


def test_handles_missing_num_parquet(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    period_dir = data_root / "2025_1" / "parquet"
    period_dir.mkdir(parents=True)
    _write_parquet(
        pd.DataFrame({"adsh": ["a1"], "cik": ["0000320193"], "form": ["10-Q"]}),
        period_dir / "sub.parquet",
    )

    audit = audit_module.audit_quarter("2025_1", data_root / "2025_1", data_root)

    assert audit.sub_exists is True
    assert audit.num_exists is False
    assert audit.known_large_cap_classification["Apple"] == "absent_from_num"


def test_classifies_absent_from_sub(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    period_dir = data_root / "2025_1" / "parquet"
    period_dir.mkdir(parents=True)
    _write_parquet(
        pd.DataFrame({"adsh": ["a1"], "cik": ["0000789019"], "form": ["10-Q"]}),
        period_dir / "sub.parquet",
    )
    _write_parquet(pd.DataFrame({"adsh": ["a1"], "value": [1.0]}), period_dir / "num.parquet")

    audit = audit_module.audit_quarter("2025_1", data_root / "2025_1", data_root)

    assert audit.known_large_cap_classification["Apple"] == "absent_from_sub"


def test_classifies_present_in_sub_but_absent_from_num(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    period_dir = data_root / "2025_2" / "parquet"
    period_dir.mkdir(parents=True)
    _write_parquet(
        pd.DataFrame({"adsh": ["a1"], "cik": ["0000320193"], "form": ["10-Q"]}),
        period_dir / "sub.parquet",
    )
    _write_parquet(pd.DataFrame({"adsh": ["other"], "value": [1.0]}), period_dir / "num.parquet")

    audit = audit_module.audit_quarter("2025_2", data_root / "2025_2", data_root)

    assert audit.known_large_cap_classification["Apple"] == "absent_from_num"


def test_writes_csv_and_summary_without_crashing(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    quarter_dir = data_root / "2025_1" / "parquet"
    quarter_dir.mkdir(parents=True)
    _write_parquet(
        pd.DataFrame(
            {
                "adsh": ["a1", "a2"],
                "cik": ["0000320193", "0000789019"],
                "form": ["10-Q", "10-K"],
            }
        ),
        quarter_dir / "sub.parquet",
    )
    _write_parquet(
        pd.DataFrame(
            {
                "adsh": ["a1", "a2"],
                "value": [100.0, 200.0],
            }
        ),
        quarter_dir / "num.parquet",
    )

    csv_out = tmp_path / "audit.csv"
    summary_out = tmp_path / "summary.md"

    exit_code = audit_module.main(
        [
            "--data-root",
            str(data_root),
            "--csv-out",
            str(csv_out),
            "--summary-out",
            str(summary_out),
        ]
    )

    assert exit_code == 0
    assert csv_out.exists()
    assert summary_out.exists()
    assert "2025_1" in summary_out.read_text(encoding="utf-8")


def test_outputs_use_sanitized_paths(tmp_path: Path) -> None:
    data_root = tmp_path / "private-data-root"
    quarter_dir = data_root / "2025_1" / "parquet"
    quarter_dir.mkdir(parents=True)
    _write_parquet(
        pd.DataFrame({"adsh": ["a1"], "cik": ["0000320193"], "form": ["10-Q"]}),
        quarter_dir / "sub.parquet",
    )
    _write_parquet(pd.DataFrame({"adsh": ["a1"], "value": [100.0]}), quarter_dir / "num.parquet")

    csv_out = tmp_path / "audit.csv"
    summary_out = tmp_path / "summary.md"
    exit_code = audit_module.main(
        [
            "--data-root",
            str(data_root),
            "--csv-out",
            str(csv_out),
            "--summary-out",
            str(summary_out),
        ]
    )

    assert exit_code == 0
    csv_text = csv_out.read_text(encoding="utf-8")
    summary_text = summary_out.read_text(encoding="utf-8")
    assert str(tmp_path) not in csv_text
    assert str(tmp_path) not in summary_text
    assert "private-data-root" in csv_text
    assert "private-data-root" in summary_text


def test_help_works_without_private_data() -> None:
    completed = subprocess.run(
        [sys.executable, str(MODULE_PATH), "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Audit SEC parquet quarter coverage and large-cap presence." in completed.stdout
