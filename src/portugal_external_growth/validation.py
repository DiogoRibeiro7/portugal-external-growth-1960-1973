"""Data contracts and cross-check reports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from portugal_external_growth.io_utils import sha256_file


@dataclass(frozen=True)
class ValidationIssue:
    """One machine-readable validation finding."""

    severity: str
    check: str
    message: str


def validate_unique(frame: pd.DataFrame, columns: list[str], *, name: str) -> list[ValidationIssue]:
    """Check that a key is unique."""

    if frame.empty:
        return [ValidationIssue("warning", f"{name}.non_empty", "Table is empty")]
    duplicates = int(frame.duplicated(columns, keep=False).sum())
    if duplicates:
        return [
            ValidationIssue(
                "error",
                f"{name}.unique_key",
                f"Found {duplicates} rows participating in duplicate keys {columns}",
            )
        ]
    return []


def validate_year_range(
    frame: pd.DataFrame,
    *,
    year_column: str,
    start_year: int,
    end_year: int,
    name: str,
) -> list[ValidationIssue]:
    """Check for observations outside the configured period."""

    if frame.empty or year_column not in frame:
        return []
    invalid = frame.loc[~frame[year_column].between(start_year, end_year)]
    if invalid.empty:
        return []
    return [
        ValidationIssue(
            "error",
            f"{name}.year_range",
            f"Found {len(invalid)} observations outside {start_year}-{end_year}",
        )
    ]


def validate_trade_shares(frame: pd.DataFrame) -> list[ValidationIssue]:
    """Check annual flow shares when a complete partner universe is available."""

    if frame.empty:
        return [ValidationIssue("warning", "trade.non_empty", "No trade table is available")]
    if "flow_share" not in frame:
        return [ValidationIssue("error", "trade.flow_share", "flow_share column is missing")]
    sums = frame.groupby(["year", "flow_code"])["flow_share"].sum(min_count=1)
    invalid = sums.loc[(sums - 1.0).abs() > 1e-8]
    if invalid.empty:
        return []
    return [
        ValidationIssue(
            "warning",
            "trade.share_sum",
            (
                "Partner-group shares do not sum to one for some years. This may indicate "
                "preview limits, missing partner records, or exclusion of World totals."
            ),
        )
    ]


def validate_preliminary_trade_shares(frame: pd.DataFrame) -> list[ValidationIssue]:
    """Validate World-denominator preliminary trade-share outputs."""

    required = {
        "year",
        "flow_code",
        "classification_scheme",
        "partner_group",
        "trade_value_usd",
        "world_value_usd",
        "world_share",
        "value_method",
    }
    missing = required.difference(frame.columns)
    if missing:
        return [
            ValidationIssue(
                "error",
                "preliminary_trade.schema",
                f"Missing preliminary trade columns: {sorted(missing)}",
            )
        ]
    issues: list[ValidationIssue] = []
    sums = frame.groupby(["year", "flow_code", "classification_scheme"])["world_share"].sum()
    invalid_sums = sums.loc[(sums - 1.0).abs() > 1e-8]
    if not invalid_sums.empty:
        issues.append(
            ValidationIssue(
                "error",
                "preliminary_trade.world_share_sum",
                "World-denominator shares must sum to one within each scheme/year/flow.",
            )
        )
    residual = frame.loc[frame["partner_group"] == "true_rest_of_world"]
    residual_counts = residual.groupby(["year", "flow_code", "classification_scheme"]).size()
    expected_groups = frame.groupby(["year", "flow_code", "classification_scheme"]).size()
    if len(residual_counts) != len(expected_groups) or (residual_counts != 1).any():
        issues.append(
            ValidationIssue(
                "error",
                "preliminary_trade.true_residual",
                "Each scheme/year/flow must contain exactly one true_rest_of_world row.",
            )
        )
    negative_residuals = residual.loc[
        pd.to_numeric(residual["trade_value_usd"], errors="coerce") < 0
    ]
    if not negative_residuals.empty:
        issues.append(
            ValidationIssue(
                "error",
                "preliminary_trade.negative_residual",
                "true_rest_of_world cannot be negative.",
            )
        )
    return issues


def build_file_manifest(root: Path) -> pd.DataFrame:
    """Create a checksum manifest for local CSV, TXT, JSON, and YAML artefacts."""

    records: list[dict[str, object]] = []
    included_roots = [root / "data", root / "results", root / "config", root / "prompts"]
    for base in included_roots:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if not path.is_file():
                continue
            if relative.startswith("results/manifests/"):
                continue
            records.append(
                {
                    "relative_path": relative,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return pd.DataFrame.from_records(records)


def issues_to_frame(issues: list[ValidationIssue]) -> pd.DataFrame:
    """Convert validation findings to a stable table."""

    if not issues:
        return pd.DataFrame([{"severity": "ok", "check": "all", "message": "All checks passed"}])
    return pd.DataFrame([issue.__dict__ for issue in issues])
