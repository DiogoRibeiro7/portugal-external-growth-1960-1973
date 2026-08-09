"""Final research-data freeze readiness and archive metadata."""

from __future__ import annotations

import json
import math
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
VERIFICATION_EVIDENCE_COLUMNS = [
    "check",
    "status",
    "command",
    "source_commit",
    "tool_version",
    "verification_timestamp_utc",
    "notes",
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
SOURCE_RELEASE_POLICY_COLUMNS = [
    "source_id",
    "expected_year",
    "source_file",
    "source_sha256",
    "source_file_status",
    "licence_status",
    "access_conditions",
    "release_distribution_decision",
    "release_include_source_file",
    "release_include_metadata",
    "release_include_derived_tables",
    "blocking_reason",
]
ARCHIVE_MANIFEST_COLUMNS = [
    "archive_path",
    "archive_sha256",
    "archive_status",
    "source_commit",
    "source_commit_timestamp_utc",
    "tracked_file_count",
    "excluded_source_file_count",
    "archived_file_count",
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
    verification_evidence_path: Path | None = None,
    create_archive: bool = False,
) -> tuple[
    pd.DataFrame,
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
    verification_evidence = build_freeze_verification_evidence(
        root,
        source_commit=commit,
        evidence_path=verification_evidence_path,
    )
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
        verification_evidence=verification_evidence,
        archive_manifest=archive_manifest,
    )
    checklist = build_freeze_checklist(
        blockers=blockers,
        verification_evidence=verification_evidence,
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
        verification_evidence,
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


def build_source_release_policy(root: Path) -> pd.DataFrame:
    """Classify local source PDFs for conservative release packaging."""

    records: list[dict[str, object]] = []
    registry = _read_csv(root / "data/manual/source_documents/source_document_registry.csv")
    registered_files: set[str] = set()
    if not registry.empty:
        for row in registry.to_dict(orient="records"):
            filenames = _split_cell(row.get("source_pdf_filename"))
            checksums = _split_cell(row.get("source_pdf_sha256"))
            for index, filename in enumerate(filenames):
                relative = f"data/manual/source_documents/{filename}"
                registered_files.add(relative)
                checksum = checksums[index] if index < len(checksums) else ""
                records.append(
                    _source_release_policy_record(
                        root,
                        source_id=str(row.get("source_id", "")),
                        expected_year=str(row.get("expected_year", "")),
                        source_file=relative,
                        source_sha256=checksum,
                        licence_status=str(row.get("licence", "")),
                        access_conditions=str(row.get("access_conditions", "")),
                        notes=str(row.get("notes", "")),
                    )
                )

    for pdf_path in sorted((root / "data/manual/source_documents").glob("*.pdf")):
        relative = pdf_path.relative_to(root).as_posix()
        if relative in registered_files:
            continue
        metadata = _read_json(pdf_path.with_suffix(pdf_path.suffix + ".metadata.json"))
        records.append(
            _source_release_policy_record(
                root,
                source_id=str(metadata.get("source_id", pdf_path.stem)),
                expected_year=str(metadata.get("expected_year", "")),
                source_file=relative,
                source_sha256=str(metadata.get("sha256", "")),
                licence_status=str(metadata.get("source_licence", "")),
                access_conditions=str(metadata.get("access_conditions", "")),
                notes=" ".join(
                    str(metadata.get(key, ""))
                    for key in ("usage_note", "source", "source_url")
                    if metadata.get(key)
                ),
            )
        )

    return pd.DataFrame.from_records(records, columns=SOURCE_RELEASE_POLICY_COLUMNS)


def build_freeze_verification_evidence(
    root: Path,
    *,
    source_commit: str,
    evidence_path: Path | None,
) -> pd.DataFrame:
    """Load machine-readable verification evidence for freeze checks."""

    required_checks = {
        "tests": "poetry run pytest --cov",
        "lint": "poetry run ruff check .",
        "format": "poetry run ruff format --check .",
        "typecheck": "poetry run mypy src tests",
        "reproduction": "poetry run peg reproduce-from-local",
        "validation": "poetry run peg validate",
        "manifest": "poetry run pytest tests/test_manifest.py",
    }
    if evidence_path is None:
        evidence_path = root / "results/releases/current/verification_evidence.csv"
    evidence_reference = repo_relative_path(evidence_path, root=root)
    if not evidence_path.exists():
        return pd.DataFrame(
            [
                {
                    "check": check,
                    "status": "missing",
                    "command": command,
                    "source_commit": source_commit,
                    "tool_version": "",
                    "verification_timestamp_utc": "",
                    "notes": f"verification evidence missing: {evidence_reference}",
                }
                for check, command in required_checks.items()
            ],
            columns=VERIFICATION_EVIDENCE_COLUMNS,
        )
    evidence = pd.read_csv(evidence_path)
    for column in VERIFICATION_EVIDENCE_COLUMNS:
        if column not in evidence:
            evidence[column] = ""
    evidence = evidence[VERIFICATION_EVIDENCE_COLUMNS].copy()
    evidence["notes"] = evidence["notes"].map(lambda value: _portable_note(value, root=root))
    recorded_checks = set(evidence["check"].astype(str))
    missing_checks = required_checks.keys() - recorded_checks
    missing_rows = [
        {
            "check": check,
            "status": "missing",
            "command": required_checks[check],
            "source_commit": source_commit,
            "tool_version": "",
            "verification_timestamp_utc": "",
            "notes": "required verification check is absent from evidence",
        }
        for check in sorted(missing_checks)
    ]
    if missing_rows:
        evidence = pd.concat(
            [evidence, pd.DataFrame.from_records(missing_rows)],
            ignore_index=True,
        )
    for index, row in evidence.iterrows():
        check = str(row["check"])
        if check not in required_checks or str(row["status"]) != "passed":
            continue
        expected_command = required_checks[check]
        if str(row["command"]) != expected_command:
            evidence.at[index, "status"] = "command_mismatch"
            evidence.at[index, "notes"] = _append_note(
                row["notes"],
                f"expected command: {expected_command}",
            )
        elif _blank_cell(row["tool_version"]):
            evidence.at[index, "status"] = "missing_tool_version"
            evidence.at[index, "notes"] = _append_note(
                row["notes"],
                "tool version is required for passed verification evidence",
            )
        elif _blank_cell(row["verification_timestamp_utc"]):
            evidence.at[index, "status"] = "missing_verification_timestamp"
            evidence.at[index, "notes"] = _append_note(
                row["notes"],
                "verification timestamp is required for passed verification evidence",
            )
    stale = evidence["source_commit"].astype(str).ne(source_commit)
    evidence.loc[stale, "status"] = "stale_commit"
    return evidence.sort_values("check").reset_index(drop=True)


def _append_note(existing: object, addition: str) -> str:
    text = "" if existing is None or existing is pd.NA else str(existing).strip()
    if not text or text.lower() in {"nan", "<na>"}:
        return addition
    return f"{text}; {addition}"


def _blank_cell(value: object) -> bool:
    if value is None or value is pd.NA:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return not str(value).strip()


def _portable_note(value: object, *, root: Path) -> str:
    if value is None or value is pd.NA:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value)
    root_resolved = root.resolve()
    replacements = (
        (root_resolved.as_posix() + "/", ""),
        (str(root_resolved) + "\\", ""),
        (root_resolved.as_posix(), "."),
        (str(root_resolved), "."),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    return text.replace("\\", "/")


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
    source_policy = build_source_release_policy(root)
    excluded_source_files = set(
        source_policy.loc[
            ~source_policy["release_include_source_file"].astype(bool), "source_file"
        ].astype(str)
    )
    archive_files = [path for path in tracked_files if path not in excluded_source_files]
    archive_path = root / "release" / f"research-data-freeze-{release_version}.zip"
    archive_sha256 = ""
    archive_status = "not_created"
    if create_archive and source_commit:
        if not archive_files:
            raise ValueError("Refusing to create an empty release archive")
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
                "--",
                *archive_files,
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
                "excluded_source_file_count": len(excluded_source_files),
                "archived_file_count": len(archive_files),
                "archive_method": "git archive HEAD -- selected release files",
                "content_scope": "tracked_files_excluding_restricted_source_documents",
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
    verification_evidence: pd.DataFrame,
    archive_manifest: pd.DataFrame,
) -> pd.DataFrame:
    """Collect machine-readable reasons preventing a paper-ready freeze."""

    records: list[dict[str, object]] = []
    failed_verification = verification_evidence.loc[~verification_evidence["status"].eq("passed")]
    for row in failed_verification.to_dict(orient="records"):
        records.append(
            _blocker(
                f"verification_{row.get('check', 'unknown')}",
                f"freeze.verification.{row.get('check', 'unknown')}",
                "not_ready",
                f"{row.get('status', 'missing')}: {row.get('notes', '')}",
                "results/releases/current/verification_evidence.csv",
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
    _append_source_redistribution_blocker(root, records)
    _append_release_scope_blockers(root, records)
    _append_transcription_blocker(root, records)
    return pd.DataFrame.from_records(records, columns=FREEZE_BLOCKER_COLUMNS)


def build_freeze_checklist(
    *,
    blockers: pd.DataFrame,
    verification_evidence: pd.DataFrame,
    dictionary_coverage: pd.DataFrame,
    table_provenance: pd.DataFrame,
    archive_manifest: pd.DataFrame,
) -> pd.DataFrame:
    """Build the Prompt 14 requirement checklist."""

    verification = {
        str(row["check"]): str(row["status"]) == "passed"
        for row in verification_evidence.to_dict(orient="records")
    }
    return pd.DataFrame.from_records(
        [
            _check("1", "All tests pass", verification.get("tests", False), "tests_not_verified"),
            _check(
                "2",
                "Linting passes",
                verification.get("lint", False) and verification.get("format", False),
                "lint_not_verified",
            ),
            _check(
                "3",
                "Type checking passes",
                verification.get("typecheck", False),
                "typecheck_not_verified",
            ),
            _check(
                "4",
                "Reproduction from local snapshots passes",
                verification.get("reproduction", False) and verification.get("validation", False),
                "reproduction_not_verified",
            ),
            _check(
                "5",
                "Manifest is deterministic",
                verification.get("manifest", False),
                "manifest_not_verified",
            ),
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
            _check(
                "12",
                "No exploratory output is mixed with release results",
                "exploratory_release_outputs_present"
                not in blockers["blocker_id"].astype(str).tolist(),
                "exploratory_release_outputs_present",
            ),
            _check(
                "13",
                "No paper prose is stored in the repository",
                "paper_prose_present" not in blockers["blocker_id"].astype(str).tolist(),
                "paper_prose_present",
            ),
            _check(
                "14",
                "Create a release archive from tracked files only",
                _release_archive_requirement_passed(
                    archive_manifest=archive_manifest,
                    blockers=blockers,
                ),
                _release_archive_requirement_reason(
                    archive_manifest=archive_manifest,
                    blockers=blockers,
                ),
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


def _release_archive_requirement_passed(
    *,
    archive_manifest: pd.DataFrame,
    blockers: pd.DataFrame,
) -> bool:
    return (
        _archive_status(archive_manifest) == "created_from_git_archive_head"
        and "source_redistribution_rights_unresolved"
        not in blockers["blocker_id"].astype(str).tolist()
    )


def _release_archive_requirement_reason(
    *,
    archive_manifest: pd.DataFrame,
    blockers: pd.DataFrame,
) -> str:
    if _archive_status(archive_manifest) != "created_from_git_archive_head":
        return "release_archive_not_created"
    if "source_redistribution_rights_unresolved" in blockers["blocker_id"].astype(str).tolist():
        return "source_redistribution_rights_unresolved"
    return ""


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
        f"Release archive: {_display_value(row.get('archive_path', ''))}",
        f"Release archive SHA-256: {_display_value(row.get('archive_sha256', ''))}",
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


def _display_value(value: object) -> str:
    text = str(value).strip()
    return text if text else "not_created"


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


def _append_release_scope_blockers(root: Path, records: list[dict[str, object]]) -> None:
    release_dir = root / "results/releases/current"
    exploratory_patterns = ("exploratory", "scratch", "temporary", "tmp", "draft")
    if release_dir.exists():
        exploratory = [
            path.relative_to(root).as_posix()
            for path in release_dir.rglob("*")
            if path.is_file()
            and any(pattern in path.name.lower() for pattern in exploratory_patterns)
        ]
        if exploratory:
            records.append(
                _blocker(
                    "exploratory_release_outputs_present",
                    "freeze.release_scope",
                    "not_ready",
                    ";".join(exploratory),
                    "results/releases/current",
                )
            )

    paper_patterns = ("paper", "manuscript", "article", "draft")
    paper_suffixes = {".md", ".tex", ".docx", ".odt", ".pdf"}
    ignored_prefixes = (
        ".github/",
        "data/",
        "results/",
        "prompts/",
        "release/",
        "dist/",
    )
    paper_files: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in paper_suffixes:
            continue
        relative = path.relative_to(root).as_posix()
        if relative in {"README.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md"}:
            continue
        if relative.startswith(ignored_prefixes):
            continue
        if any(pattern in relative.lower() for pattern in paper_patterns):
            paper_files.append(relative)
    if paper_files:
        records.append(
            _blocker(
                "paper_prose_present",
                "freeze.paper_prose",
                "not_ready",
                ";".join(sorted(paper_files)),
                ".",
            )
        )


def _append_source_redistribution_blocker(root: Path, records: list[dict[str, object]]) -> None:
    policy = build_source_release_policy(root)
    if policy.empty:
        return
    unresolved = policy.loc[policy["blocking_reason"].astype(str).ne("")]
    if unresolved.empty:
        return
    identifiers = [
        f"{row.get('source_id', '')}:{row.get('expected_year', '')}:{row.get('source_file', '')}"
        for row in unresolved.to_dict(orient="records")
    ]
    records.append(
        _blocker(
            "source_redistribution_rights_unresolved",
            "freeze.source_redistribution",
            "not_ready",
            ";".join(identifiers),
            "results/releases/current/source_release_policy.csv",
        )
    )


def _status_count(text: str, label: str) -> int:
    match = re.search(rf"^{re.escape(label)}:\s*(\d+)\s*$", text, flags=re.MULTILINE)
    if match is None:
        return 0
    return int(match.group(1))


def _source_release_policy_record(
    root: Path,
    *,
    source_id: str,
    expected_year: str,
    source_file: str,
    source_sha256: str,
    licence_status: str,
    access_conditions: str,
    notes: str,
) -> dict[str, object]:
    path = root / source_file
    source_file_status = "available" if path.exists() else "missing"
    actual_sha256 = sha256_file(path) if path.exists() else ""
    checksum = source_sha256 or actual_sha256
    text = " ".join([licence_status, access_conditions, notes]).lower()
    normalised_licence = licence_status.strip().lower()
    if "not for redistribution" in text:
        decision = "exclude_source_document_publish_metadata_and_derived_tables"
        include_source = False
        blocking_reason = "not_for_redistribution_notice"
    elif normalised_licence in {"", "not_specified"} or re.search(
        r"to_be_confirmed|licen[cs]e review|terms require.*review", text
    ):
        decision = "exclude_source_document_until_redistribution_rights_resolved"
        include_source = False
        blocking_reason = "redistribution_rights_unresolved"
    elif source_file_status == "missing":
        decision = "metadata_only_source_file_not_available"
        include_source = False
        blocking_reason = ""
    else:
        decision = "include_source_document_if_release_scope_allows"
        include_source = True
        blocking_reason = ""
    return {
        "source_id": source_id,
        "expected_year": expected_year,
        "source_file": source_file,
        "source_sha256": checksum,
        "source_file_status": source_file_status,
        "licence_status": licence_status or "not_specified",
        "access_conditions": access_conditions or "not_specified",
        "release_distribution_decision": decision,
        "release_include_source_file": include_source,
        "release_include_metadata": True,
        "release_include_derived_tables": True,
        "blocking_reason": blocking_reason,
    }


def _split_cell(value: object) -> list[str]:
    if value is None:
        return []
    text = str(value)
    if text.strip().lower() in {"", "nan", "<na>"}:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


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
