from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.io_utils import sha256_file
from portugal_external_growth.validation import (
    build_file_manifest,
    build_manual_source_document_inventory,
    build_research_readiness_report,
    issues_to_frame,
    validate_manual_transcription_source_hashes,
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
    assert manifest["relative_path"].tolist() == sorted(manifest["relative_path"].tolist())


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
    available_pdf = registry_dir / "ine_1961.pdf"
    available_pdf.write_text("source document\n", encoding="utf-8")
    available_sha256 = sha256_file(available_pdf)
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
                "source_pdf_sha256": available_sha256,
                "source_document_status": "available",
            },
        ]
    ).to_csv(registry_dir / "source_document_registry.csv", index=False)

    inventory = build_manual_source_document_inventory(tmp_path)

    assert inventory["is_available"].tolist() == [False, True]
    assert inventory["blocking_reason"].tolist() == ["sha256_not_recorded", ""]


def test_manual_source_document_inventory_verifies_local_file_and_checksum(
    tmp_path: Path,
) -> None:
    registry_dir = tmp_path / "data/manual/source_documents"
    registry_dir.mkdir(parents=True)
    valid_pdf = registry_dir / "valid.pdf"
    valid_pdf.write_text("registered source\n", encoding="utf-8")
    valid_sha256 = sha256_file(valid_pdf)
    wrong_sha256 = "0" * 64
    pd.DataFrame(
        [
            {
                "source_id": "ine",
                "title_pattern": "INE",
                "expected_year": 1960,
                "source_pdf_filename": "missing.pdf",
                "source_pdf_sha256": valid_sha256,
                "source_document_status": "registered",
            },
            {
                "source_id": "ine",
                "title_pattern": "INE",
                "expected_year": 1961,
                "source_pdf_filename": "valid.pdf",
                "source_pdf_sha256": "abc",
                "source_document_status": "registered",
            },
            {
                "source_id": "ine",
                "title_pattern": "INE",
                "expected_year": 1962,
                "source_pdf_filename": "valid.pdf",
                "source_pdf_sha256": wrong_sha256,
                "source_document_status": "registered",
            },
            {
                "source_id": "ine",
                "title_pattern": "INE",
                "expected_year": 1963,
                "source_pdf_filename": "valid.pdf",
                "source_pdf_sha256": valid_sha256,
                "source_document_status": "registered",
            },
        ]
    ).to_csv(registry_dir / "source_document_registry.csv", index=False)

    inventory = build_manual_source_document_inventory(tmp_path)

    assert inventory["is_available"].tolist() == [False, False, False, True]
    assert inventory["blocking_reason"].tolist() == [
        "file_not_found",
        "invalid_sha256",
        "sha256_mismatch",
        "",
    ]


def test_manual_source_document_inventory_accepts_verified_multi_volume_source(
    tmp_path: Path,
) -> None:
    registry_dir = tmp_path / "data/manual/source_documents"
    registry_dir.mkdir(parents=True)
    volume_i = registry_dir / "volume_i.pdf"
    volume_ii = registry_dir / "volume_ii.pdf"
    volume_i.write_text("first volume\n", encoding="utf-8")
    volume_ii.write_text("second volume\n", encoding="utf-8")
    pd.DataFrame(
        [
            {
                "source_id": "ine",
                "title_pattern": "INE",
                "expected_year": 1962,
                "source_pdf_filename": "volume_i.pdf;volume_ii.pdf",
                "source_pdf_sha256": f"{sha256_file(volume_i)};{sha256_file(volume_ii)}",
                "source_document_status": "available",
            }
        ]
    ).to_csv(registry_dir / "source_document_registry.csv", index=False)

    inventory = build_manual_source_document_inventory(tmp_path)

    assert inventory.loc[0, "is_available"]
    assert inventory.loc[0, "blocking_reason"] == ""


def test_manual_source_document_inventory_flags_multi_volume_count_mismatch(
    tmp_path: Path,
) -> None:
    registry_dir = tmp_path / "data/manual/source_documents"
    registry_dir.mkdir(parents=True)
    (registry_dir / "volume_i.pdf").write_text("first volume\n", encoding="utf-8")
    pd.DataFrame(
        [
            {
                "source_id": "ine",
                "title_pattern": "INE",
                "expected_year": 1962,
                "source_pdf_filename": "volume_i.pdf;volume_ii.pdf",
                "source_pdf_sha256": "1" * 64,
                "source_document_status": "available",
            }
        ]
    ).to_csv(registry_dir / "source_document_registry.csv", index=False)

    inventory = build_manual_source_document_inventory(tmp_path)

    assert not inventory.loc[0, "is_available"]
    assert inventory.loc[0, "blocking_reason"] == "source_file_count_mismatch"


def test_validate_manual_transcription_source_hashes_requires_registry_match(
    tmp_path: Path,
) -> None:
    registry_dir = tmp_path / "data/manual/source_documents"
    registry_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "source_id": "ine",
                "title_pattern": "INE",
                "expected_year": 1962,
                "source_pdf_filename": "ine_1962.pdf",
                "source_pdf_sha256": "1" * 64,
                "source_document_status": "registered",
            }
        ]
    ).to_csv(registry_dir / "source_document_registry.csv", index=False)
    pass_dir = tmp_path / "data/manual/transcriptions/pass_1"
    pass_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "source_id": "ine",
                "publication_year": 1962,
                "source_pdf_filename": "ine_1962.pdf",
                "source_pdf_sha256": "2" * 64,
            }
        ]
    ).to_csv(pass_dir / "ine_trade_transcription_pass_1.csv", index=False)

    issues = validate_manual_transcription_source_hashes(tmp_path)

    assert [issue.check for issue in issues] == ["manual_transcription.source_checksum_mismatch"]
