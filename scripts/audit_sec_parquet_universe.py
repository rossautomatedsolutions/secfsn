from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence

import pandas as pd


KNOWN_CIKS: Dict[str, str] = {
    "Apple": "0000320193",
    "Microsoft": "0000789019",
    "Amazon": "0001018724",
    "Meta": "0001326801",
    "Alphabet": "0001652044",
    "Nvidia": "0001045810",
    "Tesla": "0001318605",
    "JPMorgan": "0000019617",
    "Exxon": "0000034088",
}

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parents[1] / "outputs"
DEFAULT_CSV_PATH = DEFAULT_OUTPUT_DIR / "sec_parquet_universe_audit.csv"
DEFAULT_SUMMARY_PATH = DEFAULT_OUTPUT_DIR / "sec_parquet_universe_audit_summary.md"

PERIOD_RE = re.compile(r"^\d{4}_[1-4]$")


def _default_secfsn_data_root() -> Path:
    return Path(__file__).resolve().parents[2] / "secfsn" / "data"


def _format_path(path: Path, *, repo_root: Optional[Path] = None) -> str:
    resolved = path.resolve()
    if repo_root is not None:
        try:
            return resolved.relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            pass
    return resolved.name if resolved.name else str(resolved)


def _normalize_cik_series(series: pd.Series) -> pd.Series:
    return (
        series.astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.extract(r"(\d+)", expand=False)
        .fillna("")
        .str.zfill(10)
    )


def _safe_json(value: object) -> str:
    return json.dumps(value, sort_keys=True)


def _candidate_search_roots(explicit_root: Optional[Path] = None) -> List[Path]:
    roots: List[Path] = []
    seen: set[Path] = set()

    env_candidates = [
        os.environ.get("SECFSN_DATA_DIR"),
        os.environ.get("DATA_DIR"),
    ]
    raw_candidates: List[Optional[Path]] = [
        explicit_root,
        *(Path(v) for v in env_candidates if v),
        _default_secfsn_data_root(),
        Path(__file__).resolve().parents[1] / "data",
        Path(__file__).resolve().parents[2] / "data",
    ]

    for candidate in raw_candidates:
        if candidate is None:
            continue
        candidate = candidate.resolve()
        if candidate not in seen:
            roots.append(candidate)
            seen.add(candidate)

    return roots


def discover_data_root(explicit_root: Optional[Path] = None) -> tuple[Optional[Path], List[Path], List[Path]]:
    candidates = _candidate_search_roots(explicit_root=explicit_root)
    scored: List[Path] = []

    for candidate in candidates:
        if _looks_like_data_root(candidate):
            scored.append(candidate)

    if scored:
        return scored[0], scored, candidates

    search_bases = []
    for candidate in candidates:
        if candidate.exists():
            search_bases.append(candidate)
        elif candidate.parent.exists():
            search_bases.append(candidate.parent)

    seen_dirs: set[Path] = set()
    for base in search_bases:
        for found in _search_for_data_roots(base, max_depth=4):
            if found not in seen_dirs:
                scored.append(found)
                seen_dirs.add(found)

    return (scored[0] if scored else None), scored, candidates


def _looks_like_data_root(path: Path) -> bool:
    if not path.exists() or not path.is_dir():
        return False
    for child in path.iterdir():
        if PERIOD_RE.match(child.name) and (child / "parquet").is_dir():
            return True
    return False


def _search_for_data_roots(base: Path, max_depth: int) -> Iterator[Path]:
    base = base.resolve()
    if not base.exists() or not base.is_dir():
        return

    def walk(current: Path, depth: int) -> Iterator[Path]:
        if depth > max_depth:
            return
        try:
            children = [child for child in current.iterdir() if child.is_dir()]
        except OSError:
            return

        if any(PERIOD_RE.match(child.name) and (child / "parquet").is_dir() for child in children):
            yield current
            return

        for child in children:
            if child.name.startswith(".") or child.name == "__pycache__":
                continue
            yield from walk(child, depth + 1)

    yield from walk(base, 0)


@dataclass(frozen=True)
class QuarterAudit:
    quarter: str
    data_root: str
    period_dir: str
    parquet_dir: str
    sub_exists: bool
    num_exists: bool
    sub_row_count: Optional[int]
    num_row_count: Optional[int]
    distinct_cik_count_in_sub: Optional[int]
    distinct_cik_count_in_num: Optional[int]
    form_counts: Dict[str, int]
    known_large_cap_presence_in_sub: Dict[str, bool]
    known_large_cap_presence_in_num: Dict[str, bool]
    known_large_cap_presence_with_usable_numeric_rows: Dict[str, bool]
    known_large_cap_classification: Dict[str, str]

    def to_csv_row(self) -> Dict[str, object]:
        return {
            "quarter": self.quarter,
            "data_root": self.data_root,
            "period_dir": self.period_dir,
            "parquet_dir": self.parquet_dir,
            "sub_exists": self.sub_exists,
            "num_exists": self.num_exists,
            "sub_row_count": self.sub_row_count,
            "num_row_count": self.num_row_count,
            "distinct_cik_count_in_sub": self.distinct_cik_count_in_sub,
            "distinct_cik_count_in_num": self.distinct_cik_count_in_num,
            "form_counts_json": _safe_json(self.form_counts),
            "known_large_cap_presence_in_sub_json": _safe_json(self.known_large_cap_presence_in_sub),
            "known_large_cap_presence_in_num_json": _safe_json(self.known_large_cap_presence_in_num),
            "known_large_cap_presence_with_usable_numeric_rows_json": _safe_json(
                self.known_large_cap_presence_with_usable_numeric_rows
            ),
            "known_large_cap_classification_json": _safe_json(self.known_large_cap_classification),
        }


def iter_quarter_dirs(data_root: Path) -> List[tuple[str, Path]]:
    periods: List[tuple[str, Path]] = []
    if not data_root.exists():
        return periods
    for child in sorted(data_root.iterdir()):
        if child.is_dir() and PERIOD_RE.match(child.name):
            periods.append((child.name, child))
    return periods


def _read_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def _classify_company(
    company_cik: str,
    sub_df: Optional[pd.DataFrame],
    num_df: Optional[pd.DataFrame],
) -> tuple[bool, bool, bool, str]:
    if sub_df is None or "cik" not in sub_df.columns:
        return False, False, False, "absent_from_sub"

    cik_series = _normalize_cik_series(sub_df["cik"])
    sub_rows = sub_df.loc[cik_series == company_cik].copy()
    if sub_rows.empty:
        return False, False, False, "absent_from_sub"

    if num_df is None or "adsh" not in num_df.columns:
        return True, False, False, "absent_from_num"

    sub_adsh = set(sub_rows["adsh"].dropna().astype(str))
    num_adsh = num_df["adsh"].dropna().astype(str)
    matched_num = num_df.loc[num_adsh.isin(sub_adsh)].copy()
    if matched_num.empty:
        return True, False, False, "absent_from_num"

    if "value" not in matched_num.columns:
        return True, True, False, "present_in_num_but_not_usable"

    usable = pd.to_numeric(matched_num["value"], errors="coerce").notna()
    if not usable.any():
        return True, True, False, "present_in_num_but_not_usable"

    return True, True, True, "usable_numeric_rows_present"


def audit_quarter(
    period_key: str,
    period_dir: Path,
    data_root: Path,
    *,
    repo_root: Optional[Path] = None,
) -> QuarterAudit:
    parquet_dir = period_dir / "parquet"
    sub_path = parquet_dir / "sub.parquet"
    num_path = parquet_dir / "num.parquet"

    sub_exists = sub_path.exists()
    num_exists = num_path.exists()

    sub_df = _read_parquet(sub_path) if sub_exists else None
    num_df = _read_parquet(num_path) if num_exists else None

    sub_row_count = int(len(sub_df)) if sub_df is not None else None
    num_row_count = int(len(num_df)) if num_df is not None else None

    if sub_df is not None and "cik" in sub_df.columns:
        distinct_sub_ciks = int(_normalize_cik_series(sub_df["cik"]).replace("", pd.NA).dropna().nunique())
    else:
        distinct_sub_ciks = None

    distinct_num_ciks = None
    if sub_df is not None and num_df is not None and "adsh" in sub_df.columns and "adsh" in num_df.columns and "cik" in sub_df.columns:
        sub_adsh_map = sub_df[["adsh", "cik"]].dropna(subset=["adsh"]).copy()
        sub_adsh_map["cik"] = _normalize_cik_series(sub_adsh_map["cik"])
        merged = num_df[["adsh"]].dropna().merge(sub_adsh_map, on="adsh", how="left")
        distinct_num_ciks = int(merged["cik"].replace("", pd.NA).dropna().nunique())

    form_counts: Dict[str, int] = {}
    if sub_df is not None and "form" in sub_df.columns:
        form_counts = {str(k): int(v) for k, v in sub_df["form"].fillna("<null>").value_counts().to_dict().items()}

    presence_sub: Dict[str, bool] = {}
    presence_num: Dict[str, bool] = {}
    presence_usable: Dict[str, bool] = {}
    classifications: Dict[str, str] = {}
    for company, cik in KNOWN_CIKS.items():
        in_sub, in_num, usable, classification = _classify_company(cik, sub_df, num_df)
        presence_sub[company] = in_sub
        presence_num[company] = in_num
        presence_usable[company] = usable
        classifications[company] = classification

    return QuarterAudit(
        quarter=period_key,
        data_root=_format_path(data_root, repo_root=repo_root),
        period_dir=_format_path(period_dir, repo_root=repo_root),
        parquet_dir=_format_path(parquet_dir, repo_root=repo_root),
        sub_exists=sub_exists,
        num_exists=num_exists,
        sub_row_count=sub_row_count,
        num_row_count=num_row_count,
        distinct_cik_count_in_sub=distinct_sub_ciks,
        distinct_cik_count_in_num=distinct_num_ciks,
        form_counts=form_counts,
        known_large_cap_presence_in_sub=presence_sub,
        known_large_cap_presence_in_num=presence_num,
        known_large_cap_presence_with_usable_numeric_rows=presence_usable,
        known_large_cap_classification=classifications,
    )


def search_coverage_limiting_code(repo_root: Path) -> List[Dict[str, object]]:
    targeted_patterns: Dict[str, tuple[re.Pattern[str], Sequence[str]]] = {
        "form_filters": (
            re.compile(r'10-K|10-Q|forms\s*=|isin\(\["10-K", "10-Q"\]\)', re.IGNORECASE),
            ["engine", "scripts"],
        ),
        "limits_and_caps": (
            re.compile(r"max_periods|max_companies|head\(|periods\[:max_periods\]|sample_periods", re.IGNORECASE),
            ["engine", "monitoring", "scripts"],
        ),
        "quarter_restrictions": (
            re.compile(r"FSN_QUARTERS|FSN_MONTHS|month_to_quarter|combine_months_into_quarters", re.IGNORECASE),
            ["config", "fsn", "scripts"],
        ),
        "hardcoded_cik_logic": (
            re.compile(r"\bcik\b"),
            ["engine", "monitoring"],
        ),
    }
    findings: List[Dict[str, object]] = []

    for path in repo_root.rglob("*.py"):
        rel_parts = path.relative_to(repo_root).parts
        if any(part.startswith(".") for part in rel_parts):
            continue
        if rel_parts[0] == "tests":
            continue
        if path.name == "audit_sec_parquet_universe.py":
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line_no, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            for label, (pattern, allowed_roots) in targeted_patterns.items():
                if rel_parts[0] not in allowed_roots:
                    continue
                if pattern.search(line):
                    findings.append(
                        {
                            "file": _format_path(path, repo_root=repo_root),
                            "line": line_no,
                            "category": label,
                            "snippet": line.strip(),
                        }
                    )
                    break
    return findings


def write_csv(path: Path, audits: Sequence[QuarterAudit]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "quarter",
        "data_root",
        "period_dir",
        "parquet_dir",
        "sub_exists",
        "num_exists",
        "sub_row_count",
        "num_row_count",
        "distinct_cik_count_in_sub",
        "distinct_cik_count_in_num",
        "form_counts_json",
        "known_large_cap_presence_in_sub_json",
        "known_large_cap_presence_in_num_json",
        "known_large_cap_presence_with_usable_numeric_rows_json",
        "known_large_cap_classification_json",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for audit in audits:
            writer.writerow(audit.to_csv_row())


def write_summary(
    path: Path,
    selected_root: Optional[Path],
    discovered_roots: Sequence[Path],
    searched_roots: Sequence[Path],
    audits: Sequence[QuarterAudit],
    coverage_findings: Sequence[Dict[str, object]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: List[str] = []
    lines.append("# SEC Parquet Universe Audit Summary")
    lines.append("")
    lines.append(
        f"- Selected data root: `{_format_path(selected_root)}`" if selected_root else "- Selected data root: `<none found>`"
    )
    lines.append("- Search roots considered:")
    for root in searched_roots:
        lines.append(f"  - `{_format_path(root)}`")
    lines.append("- Candidate data roots:")
    if discovered_roots:
        for root in discovered_roots:
            lines.append(f"  - `{_format_path(root)}`")
    else:
        lines.append("  - `<none found>`")
    lines.append("")
    lines.append("## Quarter Audit")
    if audits:
        for audit in audits:
            lines.append(f"### {audit.quarter}")
            lines.append(f"- `sub.parquet` exists: `{audit.sub_exists}`")
            lines.append(f"- `num.parquet` exists: `{audit.num_exists}`")
            lines.append(f"- SUB rows: `{audit.sub_row_count}`")
            lines.append(f"- NUM rows: `{audit.num_row_count}`")
            lines.append(f"- Distinct CIKs in SUB: `{audit.distinct_cik_count_in_sub}`")
            lines.append(f"- Distinct CIKs in NUM: `{audit.distinct_cik_count_in_num}`")
            lines.append(f"- Form counts: `{audit.form_counts}`")
            lines.append("- Large-cap classifications:")
            for company, classification in audit.known_large_cap_classification.items():
                lines.append(f"  - `{company}`: `{classification}`")
            lines.append("")
    else:
        lines.append("No quarter parquet directories were discovered from the selected search roots.")
        lines.append("")

    lines.append("## Coverage-Limiting Code Findings")
    if coverage_findings:
        for finding in coverage_findings:
            lines.append(
                f"- `{finding['category']}` in `{finding['file']}`:{finding['line']} -> `{finding['snippet']}`"
            )
    else:
        lines.append("- No matching filters or caps found.")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit SEC parquet quarter coverage and large-cap presence.")
    parser.add_argument("--data-root", type=Path, default=None, help="Explicit SEC parquet data root to inspect.")
    parser.add_argument("--csv-out", type=Path, default=DEFAULT_CSV_PATH, help="CSV audit output path.")
    parser.add_argument("--summary-out", type=Path, default=DEFAULT_SUMMARY_PATH, help="Markdown summary output path.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    selected_root, discovered_roots, searched_roots = discover_data_root(explicit_root=args.data_root)
    audits: List[QuarterAudit] = []
    if selected_root:
        for period_key, period_dir in iter_quarter_dirs(selected_root):
            audits.append(audit_quarter(period_key, period_dir, selected_root, repo_root=repo_root))
    coverage_findings = search_coverage_limiting_code(repo_root)

    write_csv(args.csv_out, audits)
    write_summary(
        args.summary_out,
        selected_root=selected_root,
        discovered_roots=discovered_roots,
        searched_roots=searched_roots,
        audits=audits,
        coverage_findings=coverage_findings,
    )

    print(f"Wrote CSV audit to {args.csv_out}")
    print(f"Wrote summary audit to {args.summary_out}")
    if selected_root:
        print(f"Inspected data root: {selected_root}")
        print(f"Quarter count: {len(audits)}")
    else:
        print("No SEC parquet data root discovered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
