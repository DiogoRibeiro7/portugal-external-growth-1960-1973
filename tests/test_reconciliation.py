from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.reconciliation import (
    PTE_PER_USD_DIAGNOSTIC_1962,
    build_ine_comtrade_1962_notes,
    build_ine_comtrade_1962_reconciliation,
    build_reconciliation_registry,
    build_trade_reconciliation_notes,
    build_trade_source_comparison,
    finalise_trade_reconciliation,
)


def test_reconciliation_keeps_conflicting_source_values() -> None:
    comparison = pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "source": "UN Comtrade",
                "source_value": 100.0,
                "benchmark_source": "UN Comtrade",
            },
            {
                "year": 1962,
                "flow_code": "X",
                "source": "INE",
                "source_value": 90.0,
                "benchmark_source": "UN Comtrade",
            },
        ]
    )

    result = finalise_trade_reconciliation(comparison)

    assert result.loc[result["source"] == "INE", "source_value"].iloc[0] == 90.0
    assert result.loc[result["source"] == "INE", "difference_from_benchmark"].iloc[0] == -10.0


def test_trade_source_comparison_adds_missing_independent_sources(tmp_path: Path) -> None:
    audit_dir = tmp_path / "results/diagnostics/comtrade_coverage"
    audit_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "world_value_usd": 100.0,
                "territorial_definition_status": "requires_review",
            }
        ]
    ).to_csv(audit_dir / "comtrade_coverage_audit.csv", index=False)

    comparison = build_trade_source_comparison(tmp_path)

    assert set(comparison["source"]) == {"UN Comtrade", "INE", "OECD", "EFTA", "CEPII TRADHIST"}
    assert (
        comparison.loc[comparison["source"] == "UN Comtrade", "confidence_status"].iloc[0]
        == "usable_with_territorial_caveat"
    )
    assert set(comparison.loc[comparison["source"] != "UN Comtrade", "confidence_status"]) == {
        "missing_source"
    }


def test_ine_comtrade_1962_reconciliation_keeps_world_unresolved(
    tmp_path: Path,
) -> None:
    _write_ine_aggregates(tmp_path)
    _write_comtrade_1962_inputs(tmp_path)
    _write_colonial_group_config(tmp_path)

    result = build_ine_comtrade_1962_reconciliation(tmp_path)

    world_exports = result.loc[result["concept"].eq("World exports")].iloc[0]
    assert world_exports["source_a_value"] == 369792288.0
    assert world_exports["source_b_original_value"] == 10631829000.0
    assert world_exports["reconciliation_status"] == "unresolved"
    assert abs(float(world_exports["relative_difference"])) < 0.0001
    assert "exchange-rate source" in world_exports["explanation"]


def test_ine_comtrade_1962_reconciliation_resolves_with_exchange_rate_evidence(
    tmp_path: Path,
) -> None:
    _write_ine_aggregates(tmp_path)
    _write_comtrade_1962_inputs(tmp_path)
    _write_colonial_group_config(tmp_path)
    _write_historical_colonial_crosswalk(tmp_path)
    _write_exchange_rate_source(tmp_path)

    reconciliation = build_ine_comtrade_1962_reconciliation(tmp_path)
    registry = build_reconciliation_registry(reconciliation)

    world_exports = reconciliation.loc[reconciliation["concept"].eq("World exports")].iloc[0]
    overseas_exports = reconciliation.loc[reconciliation["concept"].eq("Overseas exports")].iloc[0]
    assert world_exports["reconciliation_status"] == "reconciled_with_conversion"
    assert (
        overseas_exports["reconciliation_status"]
        == "resolved_for_dataset_ine_preferred_complete_aggregate"
    )
    assert registry.loc[0, "overall_status"] == "satisfactory_with_caveats"
    assert registry.loc[0, "blocking_reasons"] == ""


def test_ine_comtrade_1962_reconciliation_marks_overseas_lower_bound(
    tmp_path: Path,
) -> None:
    _write_ine_aggregates(tmp_path)
    _write_comtrade_1962_inputs(tmp_path)
    _write_colonial_group_config(tmp_path)
    _write_historical_colonial_crosswalk(tmp_path)

    result = build_ine_comtrade_1962_reconciliation(tmp_path)

    overseas_exports = result.loc[result["concept"].eq("Overseas exports")].iloc[0]
    assert overseas_exports["source_a_value"] == 83098353.0
    assert overseas_exports["expected_partner_count"] == 8
    assert overseas_exports["observed_partner_count"] == 4
    assert overseas_exports["coverage_ratio"] == 4 / 8
    expected_value_coverage = 83098353.0 / (2390852000.0 / PTE_PER_USD_DIAGNOSTIC_1962)
    assert abs(float(overseas_exports["value_coverage_ratio"]) - expected_value_coverage) < 1e-12
    assert "portuguese_india" in overseas_exports["missing_partner_entities"]
    assert (
        overseas_exports["reconciliation_status"]
        == "resolved_for_dataset_ine_preferred_complete_aggregate"
    )
    assert "lower-bound diagnostic" in overseas_exports["explanation"]


def test_ine_comtrade_1962_notes_report_partner_and_value_coverage(
    tmp_path: Path,
) -> None:
    _write_ine_aggregates(tmp_path)
    _write_comtrade_1962_inputs(tmp_path)
    _write_colonial_group_config(tmp_path)
    _write_historical_colonial_crosswalk(tmp_path)

    notes = build_ine_comtrade_1962_notes(build_ine_comtrade_1962_reconciliation(tmp_path))

    assert "Minimum observed overseas partner coverage ratio: 0.500000" in notes
    assert "Minimum observed overseas value coverage ratio: 0.999258" in notes
    assert "source-specific eight-entity 1962 category" in notes


def test_reconciliation_registry_reports_unresolved_blockers() -> None:
    reconciliation = pd.DataFrame(
        [
            {
                "reconciliation_status": "unresolved",
                "coverage_ratio": 4 / 7,
            }
        ]
    )

    result = build_reconciliation_registry(reconciliation)

    assert result.loc[0, "overall_status"] == "unresolved"
    assert "colonial_partner_coverage_incomplete" in str(result.loc[0, "blocking_reasons"])


def test_trade_reconciliation_notes_list_missing_sources() -> None:
    comparison = pd.DataFrame(
        [
            {"source": "UN Comtrade", "confidence_status": "usable_with_territorial_caveat"},
            {"source": "INE", "confidence_status": "missing_source"},
            {"source": "CEPII TRADHIST", "confidence_status": "missing_source"},
        ]
    )

    notes = build_trade_reconciliation_notes(comparison)

    assert "CEPII TRADHIST" in notes
    assert "INE" in notes


def _write_ine_aggregates(root: Path) -> None:
    output_dir = root / "data/processed/live"
    output_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            _ine_row("M", "World", 16829535, "World imports", 29),
            _ine_row("X", "World", 10631829, "World exports", 33),
            _ine_row("M", "Ultramar", 2122236, "Overseas imports", 38),
            _ine_row("X", "Ultramar", 2390852, "Overseas exports", 39),
        ]
    ).to_csv(output_dir / "ine_aggregate_trade_harmonised.csv", index=False)


def _ine_row(
    flow: str,
    partner_group: str,
    value: int,
    table_title: str,
    page_number: int,
) -> dict[str, object]:
    return {
        "reference_year": 1962,
        "flow": flow,
        "partner_group_source": partner_group,
        "value_source": value,
        "unit_multiplier": 1000,
        "valuation_basis": "special trade",
        "territorial_definition": f"{partner_group} definition",
        "adjudication_status": "double_entry_verified",
        "page_number": page_number,
        "table_title": table_title,
    }


def _write_comtrade_1962_inputs(root: Path) -> None:
    audit_dir = root / "results/diagnostics/comtrade_coverage"
    audit_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "world_value_usd": 369792288.0,
                "territorial_definition_status": "requires_historical_metadata_review",
            },
            {
                "year": 1962,
                "flow_code": "M",
                "world_value_usd": 585345024.0,
                "territorial_definition_status": "requires_historical_metadata_review",
            },
        ]
    ).to_csv(audit_dir / "comtrade_coverage_audit.csv", index=False)
    matrix_dir = root / "data/interim/live"
    matrix_dir.mkdir(parents=True)
    rows = []
    for flow in ("X", "M"):
        values = {
            "angola": 44732692.0 if flow == "X" else 29961372.0,
            "mozambique": 18273232.0 if flow == "X" else 33201376.0,
            "guinea_bissau": 15491403.0 if flow == "X" else 10205572.0,
            "timor_leste": 4601026.0 if flow == "X" else 423914.0,
        }
        for entity_id, value in values.items():
            rows.append(
                {
                    "year": 1962,
                    "flow_code": flow,
                    "classification_code": "S1",
                    "entity_id": entity_id,
                    "trade_value_usd": value,
                }
            )
    pd.DataFrame(rows).to_csv(matrix_dir / "comtrade_coverage_matrix.csv", index=False)


def _write_colonial_group_config(root: Path) -> None:
    config_dir = root / "config"
    config_dir.mkdir()
    (config_dir / "historical_groups.yml").write_text(
        "\n".join(
            [
                "groups:",
                "  colonies:",
                "    - {entity_id: angola, start_year: 1960, end_year: 1973}",
                "    - {entity_id: cabo_verde, start_year: 1960, end_year: 1973}",
                "    - {entity_id: macao, start_year: 1960, end_year: 1973}",
                "    - {entity_id: mozambique, start_year: 1960, end_year: 1973}",
                "    - {entity_id: guinea_bissau, start_year: 1960, end_year: 1973}",
                "    - {entity_id: timor_leste, start_year: 1960, end_year: 1973}",
                "    - {entity_id: sao_tome_principe, start_year: 1960, end_year: 1973}",
            ]
        ),
        encoding="utf-8",
    )
    (config_dir / "comtrade_partner_areas.yml").write_text(
        "\n".join(
            [
                "comtrade_partner_areas:",
                _area("angola", 24),
                _area("cabo_verde", 132),
                _area("macao", 446),
                _area("mozambique", 508),
                _area("guinea_bissau", 624),
                _area("timor_leste", 626),
                _area("sao_tome_principe", 678),
            ]
        ),
        encoding="utf-8",
    )


def _write_historical_colonial_crosswalk(root: Path) -> None:
    output_dir = root / "data/interim/live"
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {"entity_id": "angola", "reference_year": 1962, "ine_group": "Ultramar Portugues"},
            {
                "entity_id": "cabo_verde",
                "reference_year": 1962,
                "ine_group": "Ultramar Portugues",
            },
            {
                "entity_id": "guinea_bissau",
                "reference_year": 1962,
                "ine_group": "Ultramar Portugues",
            },
            {"entity_id": "macao", "reference_year": 1962, "ine_group": "Ultramar Portugues"},
            {
                "entity_id": "mozambique",
                "reference_year": 1962,
                "ine_group": "Ultramar Portugues",
            },
            {
                "entity_id": "portuguese_india",
                "reference_year": 1962,
                "ine_group": "Ultramar Portugues",
            },
            {
                "entity_id": "sao_tome_principe",
                "reference_year": 1962,
                "ine_group": "Ultramar Portugues",
            },
            {
                "entity_id": "timor_leste",
                "reference_year": 1962,
                "ine_group": "Ultramar Portugues",
            },
        ]
    ).to_csv(output_dir / "historical_colonial_partner_crosswalk.csv", index=False)


def _write_exchange_rate_source(root: Path) -> None:
    source_dir = root / "data/manual/source_documents"
    source_dir.mkdir(parents=True, exist_ok=True)
    (source_dir / "imf_central_banking_legislation_portugal_ch013.pdf").write_bytes(
        b"test source placeholder"
    )


def _area(entity_id: str, code: int) -> str:
    return (
        f"  - {{entity_id: {entity_id}, entity_label: {entity_id}, m49_code: {code}, "
        f"comtrade_area_code: {code}, comtrade_area_label: {entity_id}, "
        "start_year: 1962, end_year: 1973, mapping_status: direct_area_match, "
        "mapping_source: test}"
    )
