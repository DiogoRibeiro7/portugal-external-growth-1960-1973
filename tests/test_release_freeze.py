from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from pytest import MonkeyPatch

from portugal_external_growth.release_freeze import (
    build_freeze_checklist,
    build_research_data_freeze_outputs,
    build_source_release_policy,
)


def test_research_data_freeze_declares_not_ready_with_machine_blockers(
    tmp_path: Path,
) -> None:
    _write_pyproject(tmp_path)
    _write_research_readiness(tmp_path)
    _write_empirical_audit(tmp_path)
    _write_live_result_table(tmp_path)
    _write_transcription_status(tmp_path)
    _write_analytical_dataset(tmp_path)

    declaration, blockers, checklist, provenance, dictionaries, archive, evidence, notes = (
        build_research_data_freeze_outputs(
            tmp_path,
            create_archive=False,
        )
    )

    assert declaration.loc[0, "declaration"] == "NOT_READY"
    assert "research_research.empirical_prerequisites" in blockers["blocker_id"].tolist()
    assert "final_result_table_creation_timestamps_missing" in blockers["blocker_id"].tolist()
    assert "analytical_data_dictionaries_missing" in blockers["blocker_id"].tolist()
    assert provenance.loc[0, "creation_timestamp_status"] == "missing"
    assert dictionaries["dictionary_status"].isin(["missing", "available"]).any()
    assert archive.loc[0, "archive_status"] == "not_created"
    assert set(evidence["status"]) == {"missing"}
    assert "results/releases/current/verification_evidence.csv" in ";".join(
        evidence["notes"].astype(str)
    )
    assert str(tmp_path) not in ";".join(evidence["notes"].astype(str))
    assert str(tmp_path) not in ";".join(blockers["blocking_reason"].astype(str))
    assert str(tmp_path) not in notes
    assert "verification_tests" in blockers["blocker_id"].tolist()
    assert checklist.loc[checklist["requirement_id"].eq("1"), "status"].iloc[0] == "blocked"
    assert checklist.loc[checklist["requirement_id"].eq("10"), "status"].iloc[0] == "blocked"
    assert "Declaration: NOT_READY" in notes
    assert "freeze_blocking_reasons.csv" in notes


def test_research_data_freeze_accepts_current_commit_verification_evidence(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    _write_pyproject(tmp_path)
    _write_research_readiness(tmp_path)
    _write_empirical_audit(tmp_path)
    _write_live_result_table(tmp_path)
    _write_transcription_status(tmp_path)
    _write_analytical_dataset(tmp_path)
    evidence_path = tmp_path / "verification.csv"
    source_commit = "abc123"
    pd.DataFrame(
        [
            {
                "check": check,
                "status": "passed",
                "command": command,
                "source_commit": source_commit,
                "tool_version": "test",
                "verification_timestamp_utc": "2026-08-08T00:00:00Z",
                "notes": "",
            }
            for check, command in {
                "tests": "poetry run pytest --cov",
                "lint": "poetry run ruff check .",
                "format": "poetry run ruff format --check .",
                "typecheck": "poetry run mypy src tests",
                "reproduction": "poetry run peg reproduce-from-local",
                "validation": "poetry run peg validate",
                "manifest": "poetry run pytest tests/test_manifest.py",
            }.items()
        ]
    ).to_csv(evidence_path, index=False)

    monkeypatch.setattr(
        "portugal_external_growth.release_freeze._git_stdout",
        lambda _root, args: source_commit if args == ["rev-parse", "HEAD"] else "",
    )

    _declaration, blockers, checklist, *_rest = build_research_data_freeze_outputs(
        tmp_path,
        verification_evidence_path=evidence_path,
        create_archive=False,
    )

    assert not any(str(value).startswith("verification_") for value in blockers["blocker_id"])
    assert checklist.loc[checklist["requirement_id"].eq("1"), "status"].iloc[0] == "passed"
    assert checklist.loc[checklist["requirement_id"].eq("5"), "status"].iloc[0] == "passed"


def test_research_data_freeze_rewrites_stale_evidence_notes_as_relative_paths(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    _write_pyproject(tmp_path)
    _write_research_readiness(tmp_path)
    _write_empirical_audit(tmp_path)
    _write_live_result_table(tmp_path)
    _write_transcription_status(tmp_path)
    _write_analytical_dataset(tmp_path)
    evidence_path = tmp_path / "results/releases/current/verification_evidence.csv"
    evidence_path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "check": "tests",
                "status": "missing",
                "command": "poetry run pytest --cov",
                "source_commit": "old",
                "tool_version": "",
                "verification_timestamp_utc": "",
                "notes": f"verification evidence missing: {evidence_path.as_posix()}",
            }
        ]
    ).to_csv(evidence_path, index=False)
    monkeypatch.setattr(
        "portugal_external_growth.release_freeze._git_stdout",
        lambda _root, args: "new" if args == ["rev-parse", "HEAD"] else "",
    )

    _declaration, blockers, _checklist, _provenance, _dictionaries, _archive, evidence, notes = (
        build_research_data_freeze_outputs(tmp_path, create_archive=False)
    )

    assert set(evidence["status"]) == {"missing", "stale_commit"}
    assert "results/releases/current/verification_evidence.csv" in ";".join(
        evidence["notes"].astype(str)
    )
    assert str(tmp_path) not in ";".join(evidence["notes"].astype(str))
    assert str(tmp_path) not in ";".join(blockers["blocking_reason"].astype(str))
    assert str(tmp_path) not in notes


def test_research_data_freeze_rejects_incomplete_passed_verification_evidence(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    _write_pyproject(tmp_path)
    _write_research_readiness(tmp_path)
    _write_empirical_audit(tmp_path)
    _write_live_result_table(tmp_path)
    _write_transcription_status(tmp_path)
    _write_analytical_dataset(tmp_path)
    source_commit = "abc123"
    evidence_path = tmp_path / "verification.csv"
    pd.DataFrame(
        [
            {
                "check": "tests",
                "status": "passed",
                "command": "pytest",
                "source_commit": source_commit,
                "tool_version": "pytest 8",
                "verification_timestamp_utc": "2026-08-08T00:00:00Z",
                "notes": "",
            },
            {
                "check": "lint",
                "status": "passed",
                "command": "poetry run ruff check .",
                "source_commit": source_commit,
                "tool_version": "",
                "verification_timestamp_utc": "2026-08-08T00:00:00Z",
                "notes": "",
            },
            {
                "check": "typecheck",
                "status": "passed",
                "command": "poetry run mypy src tests",
                "source_commit": source_commit,
                "tool_version": "mypy 1",
                "verification_timestamp_utc": "",
                "notes": "",
            },
        ]
    ).to_csv(evidence_path, index=False)
    monkeypatch.setattr(
        "portugal_external_growth.release_freeze._git_stdout",
        lambda _root, args: source_commit if args == ["rev-parse", "HEAD"] else "",
    )

    _declaration, blockers, checklist, *_rest = build_research_data_freeze_outputs(
        tmp_path,
        verification_evidence_path=evidence_path,
        create_archive=False,
    )

    blocker_reasons = ";".join(blockers["blocking_reason"].astype(str))
    assert "verification_tests" in blockers["blocker_id"].tolist()
    assert "command_mismatch: expected command: poetry run pytest --cov" in blocker_reasons
    assert "verification_lint" in blockers["blocker_id"].tolist()
    assert "missing_tool_version" in blocker_reasons
    assert "verification_typecheck" in blockers["blocker_id"].tolist()
    assert "missing_verification_timestamp" in blocker_reasons
    assert checklist.loc[checklist["requirement_id"].eq("1"), "status"].iloc[0] == "blocked"


def test_research_data_freeze_blocks_unresolved_source_redistribution_rights(
    tmp_path: Path,
) -> None:
    _write_pyproject(tmp_path)
    _write_research_readiness(tmp_path)
    _write_empirical_audit(tmp_path)
    _write_live_result_table(tmp_path)
    _write_transcription_status(tmp_path)
    registry = tmp_path / "data/manual/source_documents"
    registry.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "source_id": "imf",
                "expected_year": 1962,
                "source_pdf_filename": "imf.pdf",
                "licence": "to_be_confirmed_from_source",
                "access_conditions": "Not for Redistribution notice requires review",
            }
        ]
    ).to_csv(registry / "source_document_registry.csv", index=False)

    _declaration, blockers, checklist, *_rest = build_research_data_freeze_outputs(
        tmp_path,
        create_archive=False,
    )
    policy = build_source_release_policy(tmp_path)

    assert "source_redistribution_rights_unresolved" in blockers["blocker_id"].tolist()
    assert policy.loc[0, "release_distribution_decision"] == (
        "exclude_source_document_publish_metadata_and_derived_tables"
    )
    assert not bool(policy.loc[0, "release_include_source_file"])
    assert checklist.loc[checklist["requirement_id"].eq("14"), "status"].iloc[0] == "blocked"


def test_source_release_policy_excludes_unregistered_pdf_without_licence_metadata(
    tmp_path: Path,
) -> None:
    source_dir = tmp_path / "data/manual/source_documents"
    source_dir.mkdir(parents=True)
    pdf = source_dir / "imf.pdf"
    pdf.write_text("not for redistribution source\n", encoding="utf-8")
    pdf.with_suffix(".pdf.metadata.json").write_text(
        json.dumps(
            {
                "source_id": "imf",
                "sha256": "abc",
                "access_conditions": "IMF eLibrary public PDF downloaded for source verification",
                "usage_note": "Used only for exchange-rate verification.",
            }
        ),
        encoding="utf-8",
    )

    policy = build_source_release_policy(tmp_path)

    assert policy.loc[0, "source_file"] == "data/manual/source_documents/imf.pdf"
    assert policy.loc[0, "release_distribution_decision"] == (
        "exclude_source_document_until_redistribution_rights_resolved"
    )
    assert policy.loc[0, "blocking_reason"] == "redistribution_rights_unresolved"


def test_freeze_checklist_reports_source_rights_when_archive_exists() -> None:
    blockers = pd.DataFrame(
        [
            {
                "blocker_id": "source_redistribution_rights_unresolved",
                "source_check": "freeze.source_redistribution",
                "severity": "not_ready",
                "blocking_reason": "imf:1962:data/manual/source_documents/imf.pdf",
                "evidence_path": "results/releases/current/source_release_policy.csv",
            }
        ]
    )
    verification = pd.DataFrame(
        [
            {"check": check, "status": "passed"}
            for check in [
                "tests",
                "lint",
                "format",
                "typecheck",
                "reproduction",
                "validation",
                "manifest",
            ]
        ]
    )
    dictionaries = pd.DataFrame([{"dictionary_status": "available"}])
    provenance = pd.DataFrame([{"provenance_status": "complete"}])
    archive = pd.DataFrame([{"archive_status": "created_from_git_archive_head"}])

    checklist = build_freeze_checklist(
        blockers=blockers,
        verification_evidence=verification,
        dictionary_coverage=dictionaries,
        table_provenance=provenance,
        archive_manifest=archive,
    )

    release_archive = checklist.loc[checklist["requirement_id"].eq("14")].iloc[0]
    assert release_archive["status"] == "blocked"
    assert release_archive["blocking_reason"] == "source_redistribution_rights_unresolved"


def _write_pyproject(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'example'\nversion = '1.2.3'\n",
        encoding="utf-8",
    )


def _write_research_readiness(root: Path) -> None:
    path = root / "results/validation"
    path.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "severity": "not_ready",
                "check": "research.empirical_prerequisites",
                "message": "0/6 empirical prerequisites are satisfied.",
            }
        ]
    ).to_csv(path / "research_readiness_report.csv", index=False)


def _write_empirical_audit(root: Path) -> None:
    path = root / "results/live"
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "requirement": "product_level_coverage",
                "required": 1,
                "available": 0,
                "coverage": 0,
                "status": "blocked",
                "blocking_reason": "COMTRADE_SUBSCRIPTION_KEY_missing",
            }
        ]
    ).to_csv(path / "empirical_readiness_audit.csv", index=False)


def _write_live_result_table(root: Path) -> None:
    path = root / "results/live"
    path.mkdir(parents=True, exist_ok=True)
    table = path / "example_result.csv"
    table.write_text("year,value\n1962,1\n", encoding="utf-8")
    metadata = {
        "file": "results/live/example_result.csv",
        "sha256": "abc",
        "stage": "example_stage",
        "input_artifacts": [{"path": "data/input.csv", "sha256": "def"}],
    }
    table.with_suffix(table.suffix + ".metadata.json").write_text(
        json.dumps(metadata),
        encoding="utf-8",
    )


def _write_transcription_status(root: Path) -> None:
    path = root / "results/live"
    path.mkdir(parents=True, exist_ok=True)
    (path / "ine_transcription_unresolved.txt").write_text(
        "\n".join(
            [
                "Workflow status: in_progress",
                "Missing source PDFs: 1",
                "Rows without source PDF SHA-256: 1",
                "Unresolved aggregate transcription discrepancies: 1",
                "Adjudicated final rows: 0",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_analytical_dataset(root: Path) -> None:
    path = root / "data/processed/live"
    path.mkdir(parents=True)
    (path / "industry_trade_panel.csv").write_text("year,value\n1962,1\n", encoding="utf-8")
