from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.aggregate_orientation import (
    build_validated_aggregate_orientation_outputs,
)
from portugal_external_growth.pipeline import build_validated_aggregate_orientation
from portugal_external_growth.settings import Settings


def test_validated_aggregate_orientation_uses_only_verified_ine_rows(
    tmp_path: Path,
) -> None:
    _write_validated_ine_1962(tmp_path)
    _write_reconciliation(tmp_path)
    _write_registry(tmp_path)
    _write_pass_rows(tmp_path)
    _write_source_registry(tmp_path)

    dataset, status, matrix, _source_comparison, notes = (
        build_validated_aggregate_orientation_outputs(tmp_path)
    )

    row_1962 = dataset.loc[dataset["year"].eq(1962)].iloc[0]
    row_1965 = dataset.loc[dataset["year"].eq(1965)].iloc[0]
    assert row_1962["complete_colonial_export_share"] == 2390852000 / 10631829000
    assert row_1962["observed_colonial_export_share"] == 83098353 / 369792288
    assert row_1962["estimate_status"] == "observed_no_estimation"
    assert row_1965["estimate_status"] == "blocked_pending_second_pass"
    assert pd.isna(row_1965["world_exports_pte"])
    assert status.loc[status["year"].eq(1965), "blocking_reason"].iloc[0] == (
        "independent_pass_2_required"
    )
    assert set(matrix["aggregate_component"]) == {
        "World exports",
        "World imports",
        "complete colonial exports",
        "complete colonial imports",
    }
    colonial_exports = matrix.loc[
        matrix["aggregate_component"].eq("complete colonial exports")
    ].iloc[0]
    assert colonial_exports["coverage_ratio"] == 0.5
    assert abs(colonial_exports["value_coverage_ratio"] - 0.9992578581819368) < 1e-12
    assert "Complete colonial shares are never filled" in notes


def test_validated_aggregate_orientation_accepts_provincias_ultramarinas_label(
    tmp_path: Path,
) -> None:
    _write_validated_ine_1962(
        tmp_path,
        extra_rows=[
            _ine_row("M", "World", 45495031, year=1970),
            _ine_row("X", "World", 27298661, year=1970),
            _ine_row("M", "Provincias Ultramarinas", 6716990, year=1970),
            _ine_row("X", "Provincias Ultramarinas", 6687814, year=1970),
            _ine_row("M", "CEE", 15047905, year=1970),
            _ine_row("X", "CEE", 5005444, year=1970),
            _ine_row("M", "EFTA", 11023880, year=1970),
            _ine_row("X", "EFTA", 9671172, year=1970),
        ],
    )
    _write_reconciliation(tmp_path)
    _write_registry(tmp_path)
    _write_pass_rows(tmp_path)
    _write_source_registry(tmp_path)

    dataset, status, _matrix, _source_comparison, _notes = (
        build_validated_aggregate_orientation_outputs(tmp_path)
    )

    row_1970 = dataset.loc[dataset["year"].eq(1970)].iloc[0]
    status_1970 = status.loc[status["year"].eq(1970)].iloc[0]
    assert row_1970["world_exports_pte"] == 27298661000
    assert row_1970["colonial_exports_complete_pte"] == 6687814000
    assert row_1970["eec_membership_exports_pte"] == 5005444000
    assert row_1970["efta_participation_exports_pte"] == 9671172000
    assert row_1970["fixed_europe_exports_pte"] == 14676616000
    assert row_1970["complete_colonial_export_share"] == 6687814000 / 27298661000
    assert row_1970["eec_export_share"] == 5005444000 / 27298661000
    assert row_1970["efta_export_share"] == 9671172000 / 27298661000
    assert row_1970["fixed_europe_export_share"] == 14676616000 / 27298661000
    assert row_1970["estimate_status"] == "observed_no_estimation"
    assert status_1970["source_status"] == "validated_ine_aggregate"
    assert status_1970["blocking_reason"] == ""


def test_pipeline_writes_validated_aggregate_orientation_outputs(tmp_path: Path) -> None:
    _write_validated_ine_1962(tmp_path)
    _write_reconciliation(tmp_path)
    _write_registry(tmp_path)
    _write_pass_rows(tmp_path)
    _write_source_registry(tmp_path)

    build_validated_aggregate_orientation(Settings(root=tmp_path))

    assert (
        tmp_path / "data/processed/live/validated_annual_aggregate_external_orientation.csv"
    ).exists()
    assert (tmp_path / "results/live/annual_aggregate_reconciliation_matrix.csv").exists()
    assert (
        tmp_path / "results/live/annual_aggregate_external_orientation_cross_checks.txt"
    ).exists()


def _write_validated_ine_1962(
    root: Path, *, extra_rows: list[dict[str, object]] | None = None
) -> None:
    output = root / "data/processed/live"
    output.mkdir(parents=True)
    rows = [
        _ine_row("M", "World", 16829535),
        _ine_row("X", "World", 10631829),
        _ine_row("M", "Ultramar", 2122236),
        _ine_row("X", "Ultramar", 2390852),
    ]
    rows.extend(extra_rows or [])
    pd.DataFrame(rows).to_csv(output / "ine_1962_aggregate_trade_harmonised.csv", index=False)


def _ine_row(flow: str, partner_group: str, value: int, *, year: int = 1962) -> dict[str, object]:
    return {
        "reference_year": year,
        "flow": flow,
        "partner_group_source": partner_group,
        "value_source": value,
        "unit_multiplier": 1000,
        "valuation_basis": "special trade",
        "territorial_definition": "INE statistical territory",
        "adjudication_status": "double_entry_verified",
    }


def _write_reconciliation(root: Path) -> None:
    output = root / "data/interim/live"
    output.mkdir(parents=True)
    pd.DataFrame(
        [
            _reconciliation_row("World exports", 369792288, "reconciled_with_conversion"),
            _reconciliation_row("World imports", 585345024, "reconciled_with_conversion"),
            _reconciliation_row(
                "Overseas exports",
                83098353,
                "resolved_for_dataset_ine_preferred_complete_aggregate",
                coverage_ratio=0.5,
                value_coverage_ratio=0.9992578581819368,
            ),
            _reconciliation_row(
                "Overseas imports",
                73792234,
                "resolved_for_dataset_ine_preferred_complete_aggregate",
                coverage_ratio=0.5,
                value_coverage_ratio=0.9996657899969654,
            ),
        ]
    ).to_csv(output / "ine_comtrade_1962_reconciliation.csv", index=False)


def _reconciliation_row(
    concept: str,
    source_a_value: int,
    status: str,
    *,
    coverage_ratio: float | None = None,
    value_coverage_ratio: float | None = None,
) -> dict[str, object]:
    return {
        "concept": concept,
        "source_a_value": source_a_value,
        "reconciliation_status": status,
        "observed_partner_count": 4 if coverage_ratio else pd.NA,
        "expected_partner_count": 8 if coverage_ratio else pd.NA,
        "coverage_ratio": coverage_ratio if coverage_ratio else pd.NA,
        "value_coverage_ratio": value_coverage_ratio if value_coverage_ratio else pd.NA,
        "explanation": "fixture",
    }


def _write_registry(root: Path) -> None:
    output = root / "results/diagnostics/reconciliation"
    output.mkdir(parents=True)
    pd.DataFrame([{"overall_status": "satisfactory_with_caveats"}]).to_csv(
        output / "reconciliation_registry.csv",
        index=False,
    )


def _write_pass_rows(root: Path) -> None:
    pass_1 = root / "data/manual/transcriptions/pass_1"
    pass_2 = root / "data/manual/transcriptions/pass_2"
    pass_1.mkdir(parents=True)
    pass_2.mkdir(parents=True)
    pd.DataFrame([{"reference_year": 1965}]).to_csv(
        pass_1 / "ine_aggregate_transcription_pass_1.csv",
        index=False,
    )
    pd.DataFrame(columns=["reference_year"]).to_csv(
        pass_2 / "ine_aggregate_transcription_pass_2.csv",
        index=False,
    )


def _write_source_registry(root: Path) -> None:
    output = root / "data/manual/source_documents"
    output.mkdir(parents=True)
    pd.DataFrame(
        [
            {"expected_year": 1962, "source_document_status": "available"},
            {"expected_year": 1965, "source_document_status": "available"},
        ]
    ).to_csv(output / "source_document_registry.csv", index=False)
