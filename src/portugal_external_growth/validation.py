"""Data contracts and cross-check reports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from portugal_external_growth.config import load_yaml
from portugal_external_growth.io_utils import sha256_file

VALID_SHA256_RE = re.compile(r"[0-9a-fA-F]{64}")


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


def validate_manual_transcription_source_hashes(root: Path) -> list[ValidationIssue]:
    """Ensure manual transcription rows cite the registered source checksum."""

    registry_path = root / "data/manual/source_documents/source_document_registry.csv"
    if not registry_path.exists():
        return []
    registry = pd.read_csv(registry_path)
    required_registry_columns = {
        "source_id",
        "expected_year",
        "source_pdf_filename",
        "source_pdf_sha256",
    }
    if not required_registry_columns.issubset(registry.columns):
        return [
            ValidationIssue(
                "error",
                "manual_transcription.source_registry_schema",
                "Source document registry is missing checksum-reference columns.",
            )
        ]

    registry_lookup = _source_registry_checksum_lookup(registry)
    issues: list[ValidationIssue] = []
    for path in _manual_transcription_paths(root):
        if not path.exists():
            continue
        frame = pd.read_csv(path)
        if frame.empty:
            continue
        required_columns = {
            "source_id",
            "source_pdf_filename",
            "source_pdf_sha256",
        }
        has_year_column = "publication_year" in frame.columns or "reference_year" in frame.columns
        if not required_columns.issubset(frame.columns) or not has_year_column:
            issues.append(
                ValidationIssue(
                    "error",
                    "manual_transcription.source_reference_schema",
                    f"{path.relative_to(root).as_posix()} is missing source-reference columns.",
                )
            )
            continue
        missing_reference_rows = 0
        unknown_reference_rows = 0
        mismatch_rows = 0
        for row in frame.to_dict(orient="records"):
            filename = _normalise_cell(row.get("source_pdf_filename"))
            recorded_sha256 = _normalise_cell(row.get("source_pdf_sha256"))
            source_id = _normalise_cell(row.get("source_id"))
            source_year = _optional_int(row.get("reference_year"))
            if source_year is None:
                source_year = _optional_int(row.get("publication_year"))
            if source_year is None or not source_id or not filename or not recorded_sha256:
                missing_reference_rows += 1
                continue
            key = (source_id, source_year, filename)
            registry_sha256 = registry_lookup.get(key)
            if registry_sha256 is None:
                unknown_reference_rows += 1
                continue
            if recorded_sha256.lower() != registry_sha256.lower():
                mismatch_rows += 1
        relative = path.relative_to(root).as_posix()
        if missing_reference_rows:
            issues.append(
                ValidationIssue(
                    "error",
                    "manual_transcription.source_reference_missing",
                    f"{relative} has {missing_reference_rows} rows without source file/checksum.",
                )
            )
        if unknown_reference_rows:
            issues.append(
                ValidationIssue(
                    "error",
                    "manual_transcription.source_reference_unknown",
                    (
                        f"{relative} has {unknown_reference_rows} rows not found in "
                        "the source registry."
                    ),
                )
            )
        if mismatch_rows:
            issues.append(
                ValidationIssue(
                    "error",
                    "manual_transcription.source_checksum_mismatch",
                    f"{relative} has {mismatch_rows} rows with checksum mismatches.",
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
        root / "RESEARCH_DATA_READINESS.txt",
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
    return pd.DataFrame.from_records(records).sort_values("relative_path").reset_index(drop=True)


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

    registry_path = root / "results/diagnostics/reconciliation/reconciliation_registry.csv"
    if registry_path.exists():
        registry = pd.read_csv(registry_path)
        unresolved_reconciliations = registry.loc[~registry["overall_status"].eq("reconciled")]
        if not unresolved_reconciliations.empty:
            issue_ids = "; ".join(
                str(value)
                for value in unresolved_reconciliations["reconciliation_id"].dropna().unique()
            )
            issues.append(
                ValidationIssue(
                    "not_ready",
                    "research.source_reconciliation",
                    f"Unresolved source-pair reconciliation blocks remain: {issue_ids}.",
                )
            )
    else:
        issues.append(
            ValidationIssue(
                "not_ready",
                "research.source_reconciliation",
                "Source-pair reconciliation registry has not been generated.",
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
    registry["source_pdf_filename"] = (
        registry["source_pdf_filename"].astype("string").fillna("").str.strip()
    )
    registry["source_pdf_sha256"] = (
        registry["source_pdf_sha256"].astype("string").fillna("").str.strip()
    )
    source_root = source_registry_path.parent
    registry["blocking_reason"] = registry.apply(
        lambda row: _manual_document_blocking_reason(row, source_root=source_root),
        axis=1,
    )
    registry["is_available"] = registry["blocking_reason"].eq("")
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


def _manual_document_blocking_reason(row: pd.Series, *, source_root: Path) -> str:
    status = _normalise_cell(row["source_document_status"])
    if status in {"registered", "available"}:
        filenames = _split_registry_cell(row["source_pdf_filename"])
        recorded_sha256s = _split_registry_cell(row["source_pdf_sha256"])
        if not filenames:
            return "filename_not_recorded"
        if not recorded_sha256s:
            return "sha256_not_recorded"
        if len(filenames) != len(recorded_sha256s):
            return "source_file_count_mismatch"
        if any(
            VALID_SHA256_RE.fullmatch(recorded_sha256) is None
            for recorded_sha256 in recorded_sha256s
        ):
            return "invalid_sha256"
        for filename in filenames:
            pdf_path = source_root / filename
            if not pdf_path.is_file():
                return "file_not_found"
        for filename, recorded_sha256 in zip(filenames, recorded_sha256s, strict=True):
            pdf_path = source_root / filename
            if sha256_file(pdf_path).lower() != recorded_sha256.lower():
                return "sha256_mismatch"
        return ""
    if not status or status == "<NA>":
        return "source_document_status_missing"
    return status


def _source_registry_checksum_lookup(
    registry: pd.DataFrame,
) -> dict[tuple[str, int, str], str]:
    lookup: dict[tuple[str, int, str], str] = {}
    for row in registry.to_dict(orient="records"):
        source_id = _normalise_cell(row.get("source_id"))
        expected_year = _optional_int(row.get("expected_year"))
        filenames = _split_registry_cell(row.get("source_pdf_filename"))
        recorded_sha256s = _split_registry_cell(row.get("source_pdf_sha256"))
        if (
            expected_year is None
            or not source_id
            or not filenames
            or len(filenames) != len(recorded_sha256s)
        ):
            continue
        for filename, recorded_sha256 in zip(filenames, recorded_sha256s, strict=True):
            lookup[(source_id, expected_year, filename)] = recorded_sha256
    return lookup


def _manual_transcription_paths(root: Path) -> tuple[Path, ...]:
    return (
        root / "data/manual/transcriptions/pass_1/ine_trade_transcription_pass_1.csv",
        root / "data/manual/transcriptions/pass_2/ine_trade_transcription_pass_2.csv",
        root / "data/manual/transcriptions/pass_1/ine_aggregate_transcription_pass_1.csv",
        root / "data/manual/transcriptions/pass_2/ine_aggregate_transcription_pass_2.csv",
        root / "data/manual/adjudication/ine_trade_adjudicated.csv",
    )


def _normalise_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text in {"", "<NA>", "NaN", "nan", "None"}:
        return ""
    return text


def _split_registry_cell(value: object) -> list[str]:
    text = _normalise_cell(value)
    if not text:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


def _optional_int(value: object) -> int | None:
    text = _normalise_cell(value)
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    if not number.is_integer():
        return None
    return int(number)


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
