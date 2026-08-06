from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.validation import (
    build_file_manifest,
    build_manual_source_document_inventory,
    build_research_readiness_report,
    issues_to_frame,
    validate_preliminary_trade_shares,
    validate_trade_shares,
    validate_unique,
)


def test_validate_unique_reports_duplicates() -> None:
    frame = pd.DataFrame({"year": [1970, 1970], "value": [1, 2]})
    issues = validate_unique(frame, ["year"], name="example")
    assert issues[0].severity == "error"


def test_validate_trade_shares_accepts_complete_groups() -> None:
    frame = pd.DataFrame(
        {
            "year": [1970, 1970],
            "flow_code": ["X", "X"],
            "flow_share": [0.25, 0.75],
        }
    )
    assert validate_trade_shares(frame) == []


def test_validate_preliminary_trade_shares_requires_world_sum() -> None:
    frame = pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "classification_scheme": "current",
                "partner_group": "colonies",
                "trade_value_usd": 20.0,
                "world_value_usd": 100.0,
                "world_share": 0.2,
                "value_method": "selected_partner_sum",
            },
            {
                "year": 1962,
                "flow_code": "X",
                "classification_scheme": "current",
                "partner_group": "true_rest_of_world",
                "trade_value_usd": 80.0,
                "world_value_usd": 100.0,
                "world_share": 0.8,
                "value_method": "world_total_minus_selected_groups",
            },
        ]
    )
    assert validate_preliminary_trade_shares(frame) == []


def test_manifest_excludes_manifest_outputs_and_uses_posix_paths(tmp_path: Path) -> None:
    data = tmp_path / "data"
    src = tmp_path / "src/package"
    manifests = tmp_path / "results/manifests"
    data.mkdir(parents=True)
    src.mkdir(parents=True)
    manifests.mkdir(parents=True)
    (data / "table.csv").write_text("a\n1\n", encoding="utf-8")
    (data / "table.csv.metadata.json").write_text("{}\n", encoding="utf-8")
    (src / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    (manifests / "current_manifest.csv").write_text("old\n", encoding="utf-8")

    manifest = build_file_manifest(tmp_path)

    assert "data/table.csv" in manifest["relative_path"].tolist()
    assert "data/table.csv.metadata.json" in manifest["relative_path"].tolist()
    assert "src/package/module.py" in manifest["relative_path"].tolist()
    assert "pyproject.toml" in manifest["relative_path"].tolist()
    assert not any(path.startswith("results/manifests/") for path in manifest["relative_path"])


def test_empty_integrity_issues_do_not_claim_research_readiness() -> None:
    frame = issues_to_frame([])

    assert frame.loc[0, "check"] == "data_integrity.status"
    assert "All checks passed" not in str(frame.loc[0, "message"])


def test_research_readiness_reports_missing_prerequisites(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "manual_sources.yml").write_text(
        """
manual_sources:
  - source_id: ine
    title_pattern: INE
    expected_years: [1960, 1961]
""",
        encoding="utf-8",
    )

    report = build_research_readiness_report(tmp_path)

    assert "not_ready" in report["severity"].tolist()
    assert "research.manual_source_documents" in report["check"].tolist()


def test_manual_source_document_inventory_falls_back_to_config(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "manual_sources.yml").write_text(
        """
manual_sources:
  - source_id: ine
    title_pattern: INE
    expected_years: [1960, 1961]
""",
        encoding="utf-8",
    )

    inventory = build_manual_source_document_inventory(tmp_path)

    assert inventory["source_id"].tolist() == ["ine", "ine"]
    assert inventory["is_available"].tolist() == [False, False]
    assert inventory["blocking_reason"].tolist() == [
        "source_document_registry_missing",
        "source_document_registry_missing",
    ]


def test_manual_source_document_inventory_flags_incomplete_registered_metadata(
    tmp_path: Path,
) -> None:
    registry_dir = tmp_path / "data/manual/source_documents"
    registry_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "source_id": "ine",
                "title_pattern": "INE",
                "expected_year": 1960,
                "source_pdf_filename": "ine_1960.pdf",
                "source_pdf_sha256": "",
                "source_document_status": "registered",
            },
            {
                "source_id": "ine",
                "title_pattern": "INE",
                "expected_year": 1961,
                "source_pdf_filename": "ine_1961.pdf",
                "source_pdf_sha256": "abc",
                "source_document_status": "available",
            },
        ]
    ).to_csv(registry_dir / "source_document_registry.csv", index=False)

    inventory = build_manual_source_document_inventory(tmp_path)

    assert inventory["is_available"].tolist() == [False, True]
    assert inventory["blocking_reason"].tolist() == ["sha256_not_recorded", ""]
