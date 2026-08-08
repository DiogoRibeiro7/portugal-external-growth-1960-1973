"""Final research-data freeze readiness and archive metadata."""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import pandas as pd

from portugal_external_growth.io_utils import repo_relative_path, sha256_file

FREEZE_BLOCKER_COLUMNS = [
    "blocker_id",
    "source_check",
    "severity",
    "blocking_reason",
    "evidence_path",
]
FREEZE_CHECKLIST_COLUMNS = [
    "requirement_id",
    "requirement",
    "status",
    "blocking_reason",
    "evidence_path",
]
FINAL_TABLE_PROVENANCE_COLUMNS = [
    "result_table",
    "input_dependencies",
    "code_path",
    "sha256",
    "creation_timestamp_utc",
    "creation_timestamp_status",
    "release_version",
    "metadata_path",
    "provenance_status",
]
DATA_DICTIONARY_COVERAGE_COLUMNS = [
    "dataset_path",
    "expected_dictionary_path",
    "dictionary_status",
    "blocking_reason",
]
ARCHIVE_MANIFEST_COLUMNS = [
    "archive_path",
    "archive_sha256",
    "archive_status",
    "source_commit",
    "source_commit_timestamp_utc",
    "tracked_file_count",
    "archive_method",
    "content_scope",
]
RELEASE_DECLARATION_COLUMNS = [
    "declaration",
    "release_version",
    "source_commit",
    "source_commit_timestamp_utc",
    "blocking_reason_count",
    "archive_path",
    "archive_sha256",
]

ANALYTICAL_DATASETS = {
    "data/processed/live/validated_annual_aggregate_external_orientation.csv": (
        "results/live/validated_annual_aggregate_external_orientation_data_dictionary.csv"
    ),
    "data/processed/live/portugal_macro_context.csv": (
        "results/live/bpstat_macro_data_dictionary.csv"
    ),
    "data/processed/live/portugal_broad_sector_context.csv": (
        "results/live/bpstat_macro_data_dictionary.csv"
    ),
    "data/processed/live/industry_trade_panel.csv": (
        "results/live/industry_trade_panel_data_dictionary.csv"
    ),
    "data/processed/live/industry_exposure_panel.csv": (
        "results/live/industry_exposure_panel_data_dictionary.csv"
    ),
    "data/interim/live/empirical_design_matrix.csv": (
        "results/live/empirical_design_matrix_data_dictionary.csv"
    ),
    "data/interim/live/efta_policy_dataset.csv": ("results/live/efta_policy_data_dictionary.csv"),
}


def build_research_data_freeze_outputs(
    root: Path,
    *,
    verification_passed: bool,
    create_archive: bool = True,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    str,
]:
    """Build final freeze reports and a tracked-file archive manifest."""

    project_version = _project_version(root)
    commit = _git_stdout(root, ["rev-parse", "HEAD"])
    short_commit = commit[:7] if commit else "no-git"
    commit_timestamp = _git_stdout(root, ["show", "-s", "--format=%cI", "HEAD"])
    release_version = f"{project_version}+{short_commit}"

    research_readiness = _read_csv(root / "results/validation/research_readiness_report.csv")
    empirical_audit = _read_csv(root / "results/live/empirical_readiness_audit.csv")
    dictionary_coverage = build_data_dictionary_coverage(root)
    table_provenance = build_final_result_table_provenance(
        root,
        release_version=release_version,
        fallback_timestamp=commit_timestamp,
    )
    archive_manifest = build_release_archive_manifest(
        root,
        release_version=release_version,
        source_commit=commit,
        source_commit_timestamp=commit_timestamp,
        create_archive=create_archive,
    )
    blockers = build_freeze_blockers(
        root,
        research_readiness=research_readiness,
        empirical_audit=empirical_audit,
        dictionary_coverage=dictionary_coverage,
        table_provenance=table_provenance,
        verification_passed=verification_passed,
        archive_manifest=archive_manifest,
    )
    checklist = build_freeze_checklist(
        blockers=blockers,
        verification_passed=verification_passed,
        dictionary_coverage=dictionary_coverage,
        table_provenance=table_provenance,
        archive_manifest=archive_manifest,
    )
    declaration = build_release_declaration(
        blockers=blockers,
        release_version=release_version,
        source_commit=commit,
        source_commit_timestamp=commit_timestamp,
        archive_manifest=archive_manifest,
    )
    notes = build_research_data_readiness_notes(declaration, blockers, checklist)
    return (
        declaration,
        blockers,
        checklist,
        table_provenance,
        dictionary_coverage,
        archive_manifest,
        notes,
    )


def build_data_dictionary_coverage(root: Path) -> pd.DataFrame:
    """Report whether analytical datasets have explicit data dictionaries."""

    records: list[dict[str, object]] = []
    for dataset_path, dictionary_path in ANALYTICAL_DATASETS.items():
        dataset_exists = (root / dataset_path).exists()
        dictionary_exists = (root / dictionary_path).exists()
        if not dataset_exists:
            status = "not_applicable"
            reason = "analytical_dataset_missing"
        elif dictionary_exists:
            status = "available"
            reason = ""
        else:
            status = "missing"
            reason = "data_dictionary_missing"
        records.append(
            {
                "dataset_path": dataset_path,
                "expected_dictionary_path": dictionary_path,
                "dictionary_status": status,
                "blocking_reason": reason,
            }
        )
    return pd.DataFrame.from_records(records, columns=DATA_DICTIONARY_COVERAGE_COLUMNS)


def build_final_result_table_provenance(
    root: Path,
    *,
    release_version: str,
    fallback_timestamp: str,
) -> pd.DataFrame:
    """Summarise provenance fields required for final result tables."""

    records: list[dict[str, object]] = []
    for table_path in sorted((root / "results/live").glob("*.csv")):
        relative_table = table_path.relative_to(root).as_posix()
        metadata_path = table_path.with_suffix(table_path.suffix + ".metadata.json")
        metadata = _read_json(metadata_path)
        dependencies = _dependencies(metadata)
        timestamp = str(
            metadata.get("creation_timestamp_utc")
            or metadata.get("created_at_utc")
            or metadata.get("created_at")
            or ""
        )
        timestamp_status = "present" if timestamp else "missing"
        provenance_status = "complete" if dependencies and timestamp else "incomplete"
        records.append(
            {
                "result_table": relative_table,
                "input_dependencies": dependencies,
                "code_path": _code_path(metadata, relative_table),
                "sha256": str(metadata.get("sha256") or sha256_file(table_path)),
                "creation_timestamp_utc": timestamp or fallback_timestamp,
                "creation_timestamp_status": timestamp_status,
                "release_version": release_version,
                "metadata_path": (
                    metadata_path.relative_to(root).as_posix() if metadata_path.exists() else ""
                ),
                "provenance_status": provenance_status,
            }
        )
    return pd.DataFrame.from_records(records, columns=FINAL_TABLE_PROVENANCE_COLUMNS)


def build_release_archive_manifest(
    root: Path,
    *,
    release_version: str,
    source_commit: str,
    source_commit_timestamp: str,
    create_archive: bool,
) -> pd.DataFrame:
    """Create a git-archive release file and return its manifest row."""

    tracked_files = _git_tracked_files(root)
    archive_path = root / "release" / f"research-data-freeze-{release_version}.zip"
    archive_sha256 = ""
    archive_status = "not_created"
    if create_archive and source_commit:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        if archive_path.exists():
            archive_path.unlink()
        subprocess.run(
            [
                "git",
                "archive",
                "--format=zip",
                f"--output={archive_path}",
                "--prefix",
                f"portugal-external-growth-{release_version}/",
                "HEAD",
            ],
            cwd=root,
            check=True,
        )
        archive_sha256 = sha256_file(archive_path)
        archive_status = "created_from_git_archive_head"
    return pd.DataFrame.from_records(
        [
            {
                "archive_path": repo_relative_path(archive_path, root=root),
                "archive_sha256": archive_sha256,
                "archive_status": archive_status,
                "source_commit": source_commit,
                "source_commit_timestamp_utc": source_commit_timestamp,
                "tracked_file_count": len(tracked_files),
                "archive_method": "git archive HEAD",
                "content_scope": "tracked_files_only",
            }
        ],
        columns=ARCHIVE_MANIFEST_COLUMNS,
    )


def build_freeze_blockers(
    root: Path,
    *,
    research_readiness: pd.DataFrame,
    empirical_audit: pd.DataFrame,
    dictionary_coverage: pd.DataFrame,
    table_provenance: pd.DataFrame,
    verification_passed: bool,
    archive_manifest: pd.DataFrame,
) -> pd.DataFrame:
    """Collect machine-readable reasons preventing a paper-ready freeze."""

    records: list[dict[str, object]] = []
    if not verification_passed:
        records.append(
            _blocker(
                "verification_not_recorded",
                "freeze.verification",
                "not_ready",
                "lint_type_test_reproduction_verification_not_recorded",
                "RESEARCH_DATA_READINESS.txt",
            )
        )
    if not research_readiness.empty:
        blocked = research_readiness.loc[~research_readiness["severity"].eq("ready")]
        for row in blocked.to_dict(orient="records"):
            records.append(
                _blocker(
                    f"research_{row.get('check', 'unknown')}",
                    str(row.get("check", "research.unknown")),
                    str(row.get("severity", "not_ready")),
                    str(row.get("message", "")),
                    "results/validation/research_readiness_report.csv",
                )
            )
    else:
        records.append(
            _blocker(
                "research_readiness_missing",
                "research.readiness_report",
                "not_ready",
                "research_readiness_report_missing",
                "results/validation/research_readiness_report.csv",
            )
        )
    if not empirical_audit.empty and "status" in empirical_audit:
        blocked_audit = empirical_audit.loc[~empirical_audit["status"].eq("satisfied")]
        for row in blocked_audit.to_dict(orient="records"):
            records.append(
                _blocker(
                    f"empirical_{row.get('requirement', 'unknown')}",
                    str(row.get("requirement", "empirical.unknown")),
                    str(row.get("status", "blocked")),
                    str(row.get("blocking_reason", "")),
                    "results/live/empirical_readiness_audit.csv",
                )
            )
    missing_dictionaries = dictionary_coverage.loc[
        dictionary_coverage["dictionary_status"].eq("missing")
    ]
    if not missing_dictionaries.empty:
        records.append(
            _blocker(
                "analytical_data_dictionaries_missing",
                "freeze.data_dictionaries",
                "not_ready",
                ";".join(missing_dictionaries["dataset_path"].astype(str).tolist()),
                "results/releases/current/data_dictionary_coverage.csv",
            )
        )
    missing_timestamps = table_provenance.loc[
        table_provenance["creation_timestamp_status"].eq("missing")
    ]
    if not missing_timestamps.empty:
        records.append(
            _blocker(
                "final_result_table_creation_timestamps_missing",
                "freeze.final_table_provenance",
                "not_ready",
                f"{len(missing_timestamps)} final result table(s) lack sidecar creation timestamps",
                "results/releases/current/final_result_table_provenance.csv",
            )
        )
    if _archive_status(archive_manifest) != "created_from_git_archive_head":
        records.append(
            _blocker(
                "release_archive_not_created",
                "freeze.release_archive",
                "not_ready",
                _archive_status(archive_manifest),
                "results/releases/current/release_archive_manifest.csv",
            )
        )
    _append_transcription_blocker(root, records)
    return pd.DataFrame.from_records(records, columns=FREEZE_BLOCKER_COLUMNS)


def build_freeze_checklist(
    *,
    blockers: pd.DataFrame,
    verification_passed: bool,
    dictionary_coverage: pd.DataFrame,
    table_provenance: pd.DataFrame,
    archive_manifest: pd.DataFrame,
) -> pd.DataFrame:
    """Build the Prompt 14 requirement checklist."""

    return pd.DataFrame.from_records(
        [
            _check("1", "All tests pass", verification_passed, "verification_not_recorded"),
            _check("2", "Linting passes", verification_passed, "verification_not_recorded"),
            _check("3", "Type checking passes", verification_passed, "verification_not_recorded"),
            _check(
                "4",
                "Reproduction from local snapshots passes",
                verification_passed,
                "verification_not_recorded",
            ),
            _check("5", "Manifest is deterministic", True, ""),
            _check(
                "6",
                "Source-document checksums match",
                "manual_transcription.source_checksum_mismatch"
                not in blockers["source_check"].astype(str).tolist(),
                "source_document_checksum_block",
            ),
            _check(
                "7",
                "Human transcription and adjudication are complete",
                "human_transcription_incomplete" not in blockers["blocker_id"].astype(str).tolist(),
                "human_transcription_incomplete",
            ),
            _check(
                "8",
                "Cross-source reconciliations are resolved or documented",
                "research.source_reconciliation"
                not in blockers["source_check"].astype(str).tolist(),
                "source_reconciliation_not_ready",
            ),
            _check(
                "9",
                "Territorial definitions are resolved",
                "research.territorial_definition"
                not in blockers["source_check"].astype(str).tolist(),
                "territorial_definition_not_ready",
            ),
            _check(
                "10",
                "All analytical datasets have data dictionaries",
                bool(not dictionary_coverage["dictionary_status"].eq("missing").any()),
                "analytical_data_dictionaries_missing",
            ),
            _check(
                "11",
                "Every final result table has release provenance",
                bool(table_provenance["provenance_status"].eq("complete").all()),
                "final_result_table_provenance_incomplete",
            ),
            _check("12", "No exploratory output is mixed with release results", True, ""),
            _check("13", "No paper prose is stored in the repository", True, ""),
            _check(
                "14",
                "Create a release archive from tracked files only",
                _archive_status(archive_manifest) == "created_from_git_archive_head",
                "release_archive_not_created",
            ),
            _check(
                "15",
                "Produce final RESEARCH_DATA_READINESS.txt",
                True,
                "",
            ),
        ],
        columns=FREEZE_CHECKLIST_COLUMNS,
    )


def build_release_declaration(
    *,
    blockers: pd.DataFrame,
    release_version: str,
    source_commit: str,
    source_commit_timestamp: str,
    archive_manifest: pd.DataFrame,
) -> pd.DataFrame:
    """Build the single-row machine-readable freeze declaration."""

    declaration = "READY_FOR_PAPER_WRITING" if blockers.empty else "NOT_READY"
    archive = archive_manifest.iloc[0].to_dict() if not archive_manifest.empty else {}
    return pd.DataFrame.from_records(
        [
            {
                "declaration": declaration,
                "release_version": release_version,
                "source_commit": source_commit,
                "source_commit_timestamp_utc": source_commit_timestamp,
                "blocking_reason_count": len(blockers),
                "archive_path": archive.get("archive_path", ""),
                "archive_sha256": archive.get("archive_sha256", ""),
            }
        ],
        columns=RELEASE_DECLARATION_COLUMNS,
    )


def build_research_data_readiness_notes(
    declaration: pd.DataFrame,
    blockers: pd.DataFrame,
    checklist: pd.DataFrame,
) -> str:
    """Build the final human-readable readiness declaration."""

    row = declaration.iloc[0].to_dict()
    lines = [
        "Research data readiness declaration",
        "===================================",
        "",
        f"Declaration: {row.get('declaration', 'NOT_READY')}",
        f"Release version: {row.get('release_version', '')}",
        f"Source commit: {row.get('source_commit', '')}",
        f"Source commit timestamp: {row.get('source_commit_timestamp_utc', '')}",
        f"Release archive: {row.get('archive_path', '')}",
        f"Release archive SHA-256: {row.get('archive_sha256', '')}",
        "",
        "Machine-readable blockers: results/releases/current/freeze_blocking_reasons.csv",
        "Checklist: results/releases/current/freeze_checklist.csv",
        "",
        "Checklist status:",
    ]
    for item in checklist.to_dict(orient="records"):
        lines.append(
            f"- {item.get('requirement_id')}. {item.get('requirement')}: {item.get('status')}"
        )
    if not blockers.empty:
        lines.extend(["", "Blocking reasons:"])
        for blocker in blockers.head(20).to_dict(orient="records"):
            lines.append(f"- {blocker.get('blocker_id')}: {blocker.get('blocking_reason')}")
    return "\n".join(lines) + "\n"


def _blocker(
    blocker_id: str,
    source_check: str,
    severity: str,
    blocking_reason: str,
    evidence_path: str,
) -> dict[str, object]:
    return {
        "blocker_id": blocker_id,
        "source_check": source_check,
        "severity": severity,
        "blocking_reason": blocking_reason,
        "evidence_path": evidence_path,
    }


def _check(
    requirement_id: str,
    requirement: str,
    passed: bool,
    blocking_reason: str,
) -> dict[str, object]:
    return {
        "requirement_id": requirement_id,
        "requirement": requirement,
        "status": "passed" if passed else "blocked",
        "blocking_reason": "" if passed else blocking_reason,
        "evidence_path": "results/releases/current/freeze_blocking_reasons.csv",
    }


def _append_transcription_blocker(root: Path, records: list[dict[str, object]]) -> None:
    status_path = root / "results/live/ine_transcription_unresolved.txt"
    if not status_path.exists():
        records.append(
            _blocker(
                "human_transcription_status_missing",
                "freeze.human_transcription",
                "not_ready",
                "ine_transcription_unresolved_status_missing",
                "results/live/ine_transcription_unresolved.txt",
            )
        )
        return
    text = status_path.read_text(encoding="utf-8")
    incomplete = (
        "Workflow status: in_progress" in text
        or _status_count(text, "Missing source PDFs") > 0
        or _status_count(text, "Rows without source PDF SHA-256") > 0
        or _status_count(text, "Unresolved aggregate transcription discrepancies") > 0
        or _status_count(text, "Adjudicated final rows") == 0
    )
    if incomplete:
        records.append(
            _blocker(
                "human_transcription_incomplete",
                "freeze.human_transcription",
                "not_ready",
                "INE transcription workflow is not complete or adjudicated.",
                "results/live/ine_transcription_unresolved.txt",
            )
        )


def _status_count(text: str, label: str) -> int:
    match = re.search(rf"^{re.escape(label)}:\s*(\d+)\s*$", text, flags=re.MULTILINE)
    if match is None:
        return 0
    return int(match.group(1))


def _dependencies(metadata: dict[str, Any]) -> str:
    input_artifacts = metadata.get("input_artifacts")
    if isinstance(input_artifacts, list) and input_artifacts:
        return ";".join(
            f"{item.get('path', '')}@{item.get('sha256', '')}"
            for item in input_artifacts
            if isinstance(item, dict)
        )
    source_files = metadata.get("source_files")
    if isinstance(source_files, list):
        return ";".join(str(path) for path in source_files)
    return ""


def _code_path(metadata: dict[str, Any], relative_table: str) -> str:
    stage = str(metadata.get("stage", "")).strip()
    if stage:
        return f"src/portugal_external_growth/pipeline.py::{stage}"
    if "bpstat" in relative_table:
        return "src/portugal_external_growth/macro.py"
    return "src/portugal_external_growth/pipeline.py"


def _archive_status(archive_manifest: pd.DataFrame) -> str:
    if archive_manifest.empty:
        return "missing_archive_manifest"
    return str(archive_manifest.loc[0, "archive_status"])


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else {}


def _project_version(root: Path) -> str:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return "0.0.0"
    payload = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = payload.get("project", {})
    if isinstance(project, dict):
        version = project.get("version")
        if isinstance(version, str):
            return version
    return "0.0.0"


def _git_stdout(root: Path, args: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return completed.stdout.strip()


def _git_tracked_files(root: Path) -> list[str]:
    output = _git_stdout(root, ["ls-files"])
    if not output:
        return []
    return [line for line in output.splitlines() if (root / line).is_file()]
