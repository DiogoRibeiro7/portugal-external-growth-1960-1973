"""Data contracts and cross-check reports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from portugal_external_growth.config import load_yaml
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
    residual_labels = {"true_rest_of_world", "unassigned_world_residual"}
    residual = frame.loc[frame["partner_group"].isin(residual_labels)]
    residual_counts = residual.groupby(["year", "flow_code", "classification_scheme"]).size()
    expected_groups = frame.groupby(["year", "flow_code", "classification_scheme"]).size()
    if len(residual_counts) != len(expected_groups) or (residual_counts != 1).any():
        issues.append(
            ValidationIssue(
                "error",
                "preliminary_trade.residual",
                "Each scheme/year/flow must contain exactly one World residual row.",
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
                "World residual cannot be negative.",
            )
        )
    return issues


def build_file_manifest(root: Path) -> pd.DataFrame:
    """Create a checksum manifest for data, results, code, tests, and dependencies."""

    records: list[dict[str, object]] = []
    included_roots = [
        root / "data",
        root / "results",
        root / "config",
        root / "prompts",
        root / "src",
        root / "tests",
        root / ".github",
    ]
    for base in included_roots:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            relative = path.relative_to(root).as_posix()
            if not path.is_file():
                continue
            if _excluded_from_manifest(path, relative):
                continue
            records.append(
                {
                    "relative_path": relative,
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                    "artifact_role": _artifact_role(relative),
                }
            )
    for path in [
        root / "pyproject.toml",
        root / "poetry.lock",
        root / "README.md",
        root / "DATA_LICENSES.md",
        root / "Makefile",
    ]:
        if not path.exists():
            continue
        records.append(
            {
                "relative_path": path.relative_to(root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
                "artifact_role": _artifact_role(path.name),
            }
        )
    return pd.DataFrame.from_records(records)


def _excluded_from_manifest(path: Path, relative_path: str) -> bool:
    if relative_path.startswith("results/manifests/"):
        return True
    if "__pycache__" in path.parts:
        return True
    return path.suffix in {".pyc", ".pyo"}


def issues_to_frame(issues: list[ValidationIssue]) -> pd.DataFrame:
    """Convert validation findings to a stable table."""

    if not issues:
        return pd.DataFrame(
            [
                {
                    "severity": "ok",
                    "check": "data_integrity.status",
                    "message": "Data-integrity checks passed.",
                }
            ]
        )
    return pd.DataFrame([issue.__dict__ for issue in issues])


def has_error(issues: list[ValidationIssue]) -> bool:
    """Return whether any validation issue should fail the command."""

    return any(issue.severity == "error" for issue in issues)


def build_research_readiness_report(root: Path) -> pd.DataFrame:
    """Report whether current artefacts are sufficient for empirical interpretation."""

    issues: list[ValidationIssue] = []
    prerequisite_path = root / "results/live/empirical_prerequisite_status.csv"
    if prerequisite_path.exists():
        prerequisites = pd.read_csv(prerequisite_path)
        satisfied = int(prerequisites["status"].eq("satisfied").sum())
        total = len(prerequisites)
    else:
        satisfied = 0
        total = 6
    if satisfied < total:
        issues.append(
            ValidationIssue(
                "not_ready",
                "research.empirical_prerequisites",
                f"{satisfied}/{total} empirical prerequisites are satisfied.",
            )
        )

    expected_documents = _expected_manual_document_count(root)
    document_inventory = build_manual_source_document_inventory(root)
    available_documents = int(document_inventory["is_available"].sum())
    if available_documents < expected_documents:
        issues.append(
            ValidationIssue(
                "not_ready",
                "research.manual_source_documents",
                (
                    f"{available_documents}/{expected_documents} expected manual source "
                    "documents are available."
                ),
            )
        )

    comparison_path = root / "data/interim/live/trade_source_comparison.csv"
    if comparison_path.exists():
        comparison = pd.read_csv(comparison_path)
        missing_rows = int(
            comparison.astype("string")
            .apply(lambda column: column.str.contains("missing", case=False, na=False))
            .any(axis=1)
            .sum()
        )
        if missing_rows:
            issues.append(
                ValidationIssue(
                    "not_ready",
                    "research.cross_source_comparison",
                    (
                        f"{missing_rows}/{len(comparison)} cross-source comparison rows have "
                        "missing source coverage."
                    ),
                )
            )
    else:
        issues.append(
            ValidationIssue(
                "not_ready",
                "research.cross_source_comparison",
                "Cross-source comparison table has not been generated.",
            )
        )

    mapping_path = root / "results/live/sitc_mapping_coverage.csv"
    if mapping_path.exists():
        mapping = pd.read_csv(mapping_path)
        max_coverage = float(
            pd.to_numeric(
                mapping.get("mapping_coverage_share", pd.Series(dtype=float)), errors="coerce"
            )
            .fillna(0.0)
            .max()
        )
    else:
        max_coverage = 0.0
    if max_coverage <= 0.0:
        issues.append(
            ValidationIssue(
                "not_ready",
                "research.product_industry_mapping",
                "Product-to-industry mapping coverage is zero.",
            )
        )

    audit_path = root / "results/diagnostics/comtrade_coverage/comtrade_coverage_audit.csv"
    if audit_path.exists():
        audit = pd.read_csv(audit_path)
        unresolved = int(
            audit.get("territorial_definition_status", pd.Series(dtype=object))
            .astype("string")
            .ne("resolved")
            .sum()
        )
        if unresolved:
            issues.append(
                ValidationIssue(
                    "not_ready",
                    "research.territorial_definition",
                    (
                        f"{unresolved} Comtrade coverage rows still require "
                        "territorial-definition review."
                    ),
                )
            )
    else:
        issues.append(
            ValidationIssue(
                "not_ready",
                "research.territorial_definition",
                "Comtrade coverage audit has not been generated.",
            )
        )

    design_path = root / "data/interim/live/empirical_design_matrix.csv"
    if not design_path.exists() or pd.read_csv(design_path).empty:
        issues.append(
            ValidationIssue(
                "not_ready",
                "research.empirical_design_matrix",
                "No empirical design matrix exists.",
            )
        )

    if issues:
        return pd.DataFrame([issue.__dict__ for issue in issues])
    return pd.DataFrame(
        [
            {
                "severity": "ready",
                "check": "research.status",
                "message": "Research-readiness checks passed.",
            }
        ]
    )


def build_manual_source_document_inventory(root: Path) -> pd.DataFrame:
    """Summarise manual source-document availability for validation reports."""

    columns = [
        "source_id",
        "title_pattern",
        "expected_year",
        "source_pdf_filename",
        "source_pdf_sha256",
        "source_document_status",
        "is_available",
        "blocking_reason",
    ]
    source_registry_path = root / "data/manual/source_documents/source_document_registry.csv"
    if not source_registry_path.exists():
        return _manual_document_inventory_from_config(root, columns)

    registry = pd.read_csv(source_registry_path)
    for column in columns:
        if column not in registry:
            registry[column] = ""
    registry["source_document_status"] = registry["source_document_status"].astype("string")
    registry["source_pdf_filename"] = registry["source_pdf_filename"].astype("string").fillna("")
    registry["source_pdf_sha256"] = registry["source_pdf_sha256"].astype("string").fillna("")
    has_registered_status = registry["source_document_status"].isin(["registered", "available"])
    has_filename = registry["source_pdf_filename"].str.len() > 0
    has_checksum = registry["source_pdf_sha256"].str.len() > 0
    registry["is_available"] = has_registered_status & has_filename & has_checksum
    registry["blocking_reason"] = registry.apply(_manual_document_blocking_reason, axis=1)
    return (
        registry[columns]
        .sort_values(["source_id", "expected_year"], na_position="last")
        .reset_index(drop=True)
    )


def _manual_document_inventory_from_config(root: Path, columns: list[str]) -> pd.DataFrame:
    config_path = root / "config/manual_sources.yml"
    if not config_path.exists():
        return pd.DataFrame(columns=columns)
    payload = load_yaml(config_path)
    sources = payload.get("manual_sources")
    if not isinstance(sources, list):
        return pd.DataFrame(columns=columns)
    records: list[dict[str, object]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        expected_years = source.get("expected_years")
        if not isinstance(expected_years, list):
            continue
        for year in expected_years:
            records.append(
                {
                    "source_id": source.get("source_id", ""),
                    "title_pattern": source.get("title_pattern", ""),
                    "expected_year": int(year),
                    "source_pdf_filename": "",
                    "source_pdf_sha256": "",
                    "source_document_status": "missing_source_registry",
                    "is_available": False,
                    "blocking_reason": "source_document_registry_missing",
                }
            )
    return pd.DataFrame.from_records(records, columns=columns)


def _manual_document_blocking_reason(row: pd.Series) -> str:
    status = str(row["source_document_status"])
    if status in {"registered", "available"}:
        if not str(row["source_pdf_filename"]):
            return "filename_not_recorded"
        if not str(row["source_pdf_sha256"]):
            return "sha256_not_recorded"
        return ""
    if not status or status == "<NA>":
        return "source_document_status_missing"
    return status


def _artifact_role(relative_path: str) -> str:
    if relative_path.startswith(("src/", "tests/")):
        return "implementation"
    if relative_path.startswith(".github/") or relative_path in {"pyproject.toml", "poetry.lock"}:
        return "execution_environment"
    if relative_path.startswith("config/"):
        return "configuration"
    if relative_path.startswith("data/"):
        return "data"
    if relative_path.startswith("results/"):
        return "result"
    if relative_path.startswith("prompts/"):
        return "workflow_instruction"
    return "documentation"


def _expected_manual_document_count(root: Path) -> int:
    config_path = root / "config/manual_sources.yml"
    if not config_path.exists():
        return 0
    payload = load_yaml(config_path)
    sources = payload.get("manual_sources")
    if not isinstance(sources, list):
        return 0
    return sum(
        len(source.get("expected_years", []))
        for source in sources
        if isinstance(source, dict) and isinstance(source.get("expected_years"), list)
    )
