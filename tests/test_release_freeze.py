from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from portugal_external_growth.release_freeze import build_research_data_freeze_outputs


def test_research_data_freeze_declares_not_ready_with_machine_blockers(
    tmp_path: Path,
) -> None:
    _write_pyproject(tmp_path)
    _write_research_readiness(tmp_path)
    _write_empirical_audit(tmp_path)
    _write_live_result_table(tmp_path)
    _write_transcription_status(tmp_path)
    _write_analytical_dataset(tmp_path)

    declaration, blockers, checklist, provenance, dictionaries, archive, notes = (
        build_research_data_freeze_outputs(
            tmp_path,
            verification_passed=True,
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
    assert checklist.loc[checklist["requirement_id"].eq("10"), "status"].iloc[0] == "blocked"
    assert "Declaration: NOT_READY" in notes
    assert "freeze_blocking_reasons.csv" in notes


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
