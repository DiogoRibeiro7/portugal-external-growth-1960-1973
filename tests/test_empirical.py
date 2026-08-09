from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.empirical import (
    build_empirical_prerequisite_status,
    build_empirical_readiness_audit,
    build_empirical_readiness_audit_notes,
    build_empirical_risk_notes,
    build_model_specification_registry,
    empty_coefficients,
    empty_design_matrix,
    empty_diagnostics,
    empty_identification_strategy_review,
    load_empirical_design_matrix_or_empty,
)


def test_empirical_prerequisites_are_blocked_by_default() -> None:
    status = build_empirical_prerequisite_status()
    assert set(status["status"]) == {"not_satisfied"}


def test_empirical_coefficients_are_empty() -> None:
    coefficients = empty_coefficients()
    assert coefficients.empty
    assert "estimate" in coefficients.columns


def test_empirical_placeholder_outputs_are_schema_stable() -> None:
    design = empty_design_matrix()
    diagnostics = empty_diagnostics()
    specs = build_model_specification_registry()
    notes = build_empirical_risk_notes()

    assert design.empty
    assert "colonial_exposure" in design.columns
    assert diagnostics.loc[0, "status"] == "failed"
    assert set(specs["status"]) == {"blocked_pending_prerequisites"}
    assert "No model has been fit" in notes


def test_empirical_readiness_audit_blocks_empty_repository(tmp_path: Path) -> None:
    audit = build_empirical_readiness_audit(tmp_path)
    notes = build_empirical_readiness_audit_notes(audit)

    assert len(audit) == 15
    assert set(audit["status"]) == {"blocked"}
    assert audit.loc[audit["requirement"].eq("product_level_coverage"), "coverage"].iloc[0] == 0
    assert "No causal regressions" in notes


def test_empirical_readiness_audit_uses_available_artifacts(tmp_path: Path) -> None:
    processed = tmp_path / "data/processed/live"
    diagnostics = tmp_path / "results/diagnostics"
    live = tmp_path / "results/live"
    interim = tmp_path / "data/interim/live"
    processed.mkdir(parents=True)
    (diagnostics / "reconciliation").mkdir(parents=True)
    (diagnostics / "comtrade_coverage").mkdir(parents=True)
    (diagnostics / "product_industry_mapping").mkdir(parents=True)
    (diagnostics / "industry_exposure").mkdir(parents=True)
    live.mkdir(parents=True)
    interim.mkdir(parents=True)

    pd.DataFrame(
        [
            {
                "year": year,
                "flow_code": flow,
                "colonial_exports_complete_pte": 1.0 if flow == "X" else None,
                "colonial_imports_complete_pte": 1.0 if flow == "M" else None,
                "efta_participation_exports_pte": 1.0 if flow == "X" else None,
                "efta_participation_imports_pte": 1.0 if flow == "M" else None,
                "eec_membership_exports_pte": 1.0 if flow == "X" else None,
                "eec_membership_imports_pte": 1.0 if flow == "M" else None,
                "fixed_europe_exports_pte": 1.0 if flow == "X" else None,
                "fixed_europe_imports_pte": 1.0 if flow == "M" else None,
            }
            for year in range(1962, 1974)
            for flow in ["X", "M"]
        ]
    ).to_csv(processed / "validated_annual_aggregate_external_orientation.csv", index=False)
    pd.DataFrame(
        [
            {
                "status": "ready",
                "normalised_rows": 10,
                "blocking_reason": "",
            }
        ]
    ).to_csv(live / "comtrade_product_extraction_status.csv", index=False)
    pd.DataFrame(
        [
            {
                "status": "ready",
                "max_mapping_coverage_share": 1.0,
                "blocking_reason": "",
            }
        ]
    ).to_csv(diagnostics / "product_industry_mapping/product_mapping_status.csv", index=False)
    pd.DataFrame(
        [
            {"target_industry_code": industry, "year": year}
            for year in range(1962, 1974)
            for industry in ["agriculture", "manufacturing"]
        ]
    ).to_csv(processed / "industry_trade_panel.csv", index=False)
    pd.DataFrame([{"status": "available"}, {"status": "available"}]).to_csv(
        diagnostics / "industry_exposure/industry_exposure_coverage.csv", index=False
    )
    pd.DataFrame(
        [
            {"year": year, "flow_code": flow, "territorial_definition_status": "resolved"}
            for year in range(1962, 1974)
            for flow in ["X", "M"]
        ]
    ).to_csv(diagnostics / "comtrade_coverage/comtrade_coverage_audit.csv", index=False)
    pd.DataFrame(
        [{"overall_status": "satisfactory_with_caveats"} for _source_scope in range(4)]
    ).to_csv(diagnostics / "reconciliation/reconciliation_registry.csv", index=False)
    pd.DataFrame(
        [
            {
                "series": "manufacturing GVA",
                "concept": "manufacturing_value_added",
                "analytical_use": "empirical_identification",
            },
            {
                "series": "GDP deflator price",
                "concept": "gdp_deflator",
                "analytical_use": "empirical_identification",
            },
        ]
    ).to_csv(live / "bpstat_macro_data_dictionary.csv", index=False)
    pd.DataFrame(
        [
            {
                "year": 1962,
                "colonial_exposure": 0.2,
                "european_exposure": 0.3,
                "controls_available": True,
            },
            {
                "year": 1963,
                "colonial_exposure": 0.25,
                "european_exposure": 0.35,
                "controls_available": True,
            },
        ]
    ).to_csv(interim / "empirical_design_matrix.csv", index=False)
    (tmp_path / "config").mkdir()
    (tmp_path / "config/product_industry_mapping.yml").write_text(
        "\n".join(
            [
                "mapping_version: test",
                "mapping_status: ready",
                "mappings:",
                "  - source_classification: S2",
                '    commodity_code: "001"',
                "    target_industry_code: agriculture",
            ]
        ),
        encoding="utf-8",
    )
    (diagnostics / "comtrade_product").mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "classification_code": "S2",
                "commodity_code": "001",
                "partner_count": 1,
                "reported_rows": 1,
                "original_classification_rows": 1,
                "estimated_rows": 0,
                "aggregate_rows": 0,
                "trade_value_usd": 100.0,
                "coverage_status": "reported_product_rows",
            }
        ]
    ).to_csv(
        diagnostics / "comtrade_product/product_coverage_diagnostics.csv",
        index=False,
    )
    (live / "product_industry_mapping_documentation.txt").write_text(
        "Status: ready\nHistorical classification breaks documented for S2 product rows.\n",
        encoding="utf-8",
    )

    audit = build_empirical_readiness_audit(tmp_path)

    satisfied = set(audit.loc[audit["status"].eq("satisfied"), "requirement"])
    assert "annual_trade_coverage" in satisfied
    assert "product_level_coverage" in satisfied
    assert "product_to_industry_mapping_coverage" in satisfied
    assert "sectoral_output_coverage" in satisfied
    assert "price_deflator_coverage" in satisfied
    assert "territorial_consistency" in satisfied
    assert "cross_source_reconciliation" in satisfied
    assert "usable_industries" in satisfied
    assert "usable_years" in satisfied
    assert "classification_breaks_documented" in satisfied
    assert "identification_variables_available" in satisfied

    pd.DataFrame(
        [
            {"strategy_component": "simultaneity", "status": "satisfied", "blocking_reason": ""},
            {
                "strategy_component": "common_european_shocks",
                "status": "satisfied",
                "blocking_reason": "",
            },
        ]
    ).to_csv(live / "identification_strategy_review.csv", index=False)

    prerequisites = build_empirical_prerequisite_status(tmp_path)

    assert set(prerequisites["status"]) == {"satisfied"}


def test_empirical_design_matrix_loader_preserves_existing_matrix(tmp_path: Path) -> None:
    path = tmp_path / "data/interim/live"
    path.mkdir(parents=True)
    existing = pd.DataFrame(
        [
            {
                "year": 1962,
                "sector_code": "textiles",
                "outcome_variable": "output_growth",
                "colonial_exposure": 0.2,
                "european_exposure": 0.3,
                "controls_available": True,
                "source_quality": "reviewed",
            }
        ]
    )
    existing.to_csv(path / "empirical_design_matrix.csv", index=False)

    loaded = load_empirical_design_matrix_or_empty(tmp_path)

    assert loaded.equals(existing)


def test_empty_identification_strategy_review_blocks_by_default() -> None:
    review = empty_identification_strategy_review()

    assert set(review["status"]) == {"blocked"}
    assert set(review["strategy_component"]) == {"simultaneity", "common_european_shocks"}


def test_macro_controls_require_empirical_use_review_flags(tmp_path: Path) -> None:
    live = tmp_path / "results/live"
    live.mkdir(parents=True)
    pd.DataFrame(
        [
            {"series": "manufacturing GVA", "concept": "manufacturing_value_added"},
            {"series": "GDP deflator price", "concept": "gdp_deflator"},
        ]
    ).to_csv(live / "bpstat_macro_data_dictionary.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    sectoral = audit.loc[audit["requirement"].eq("sectoral_output_coverage")].iloc[0]
    deflator = audit.loc[audit["requirement"].eq("price_deflator_coverage")].iloc[0]
    assert sectoral["status"] == "blocked"
    assert deflator["status"] == "blocked"
    assert "empirical-use review flags" in sectoral["blocking_reason"]
    assert "empirical-use review flags" in deflator["blocking_reason"]


def test_empirical_audit_uses_full_territorial_and_reconciliation_denominators(
    tmp_path: Path,
) -> None:
    diagnostics = tmp_path / "results/diagnostics"
    (diagnostics / "comtrade_coverage").mkdir(parents=True)
    (diagnostics / "reconciliation").mkdir(parents=True)
    processed = tmp_path / "data/processed/live"
    processed.mkdir(parents=True)

    pd.DataFrame([{"territorial_definition_status": "resolved"}]).to_csv(
        diagnostics / "comtrade_coverage/comtrade_coverage_audit.csv",
        index=False,
    )
    pd.DataFrame([{"overall_status": "satisfactory_with_caveats"}]).to_csv(
        diagnostics / "reconciliation/reconciliation_registry.csv",
        index=False,
    )
    pd.DataFrame([{"target_industry_code": "agriculture", "year": 1962}]).to_csv(
        processed / "industry_trade_panel.csv",
        index=False,
    )

    audit = build_empirical_readiness_audit(tmp_path)

    territorial = audit.loc[audit["requirement"].eq("territorial_consistency")].iloc[0]
    reconciliation = audit.loc[audit["requirement"].eq("cross_source_reconciliation")].iloc[0]
    industries = audit.loc[audit["requirement"].eq("usable_industries")].iloc[0]
    assert territorial["required"] == 24
    assert territorial["available"] == 1
    assert territorial["status"] == "blocked"
    assert reconciliation["required"] == 4
    assert reconciliation["available"] == 1
    assert reconciliation["status"] == "blocked"
    assert industries["required"] == 2
    assert industries["available"] == 1
    assert industries["status"] == "blocked"


def test_partner_completeness_uses_year_flow_denominators(tmp_path: Path) -> None:
    processed = tmp_path / "data/processed/live"
    processed.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "year": year,
                "colonial_exports_complete_pte": float(year) if year < 1968 else None,
                "colonial_imports_complete_pte": float(year) if year < 1968 else None,
                "colonial_observed_partner_count": 4,
                "colonial_expected_partner_count": 8,
                "efta_participation_exports_pte": float(year) if year < 1968 else None,
                "efta_participation_imports_pte": float(year) if year < 1968 else None,
                "eec_membership_exports_pte": None,
                "eec_membership_imports_pte": None,
                "fixed_europe_exports_pte": None,
                "fixed_europe_imports_pte": None,
            }
            for year in range(1962, 1974)
        ]
    ).to_csv(processed / "validated_annual_aggregate_external_orientation.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    colonial = audit.loc[audit["requirement"].eq("colonial_partner_completeness")].iloc[0]
    european = audit.loc[audit["requirement"].eq("european_partner_completeness")].iloc[0]
    assert colonial["required"] == 24
    assert colonial["available"] == 12
    assert colonial["status"] == "blocked"
    assert european["required"] == 24
    assert european["available"] == 12
    assert european["status"] == "blocked"


def test_partner_completeness_uses_fixed_sample_denominator_for_long_partial_panel(
    tmp_path: Path,
) -> None:
    processed = tmp_path / "data/processed/live"
    processed.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "colonial_exports_complete_pte": 10.0,
                "colonial_imports_complete_pte": None,
                "efta_participation_exports_pte": 5.0,
                "efta_participation_imports_pte": None,
            },
            {
                "year": 1962,
                "flow_code": "M",
                "colonial_exports_complete_pte": None,
                "colonial_imports_complete_pte": 8.0,
                "efta_participation_exports_pte": None,
                "efta_participation_imports_pte": 4.0,
            },
        ]
    ).to_csv(processed / "validated_annual_aggregate_external_orientation.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    annual = audit.loc[audit["requirement"].eq("annual_trade_coverage")].iloc[0]
    colonial = audit.loc[audit["requirement"].eq("colonial_partner_completeness")].iloc[0]
    european = audit.loc[audit["requirement"].eq("european_partner_completeness")].iloc[0]
    assert annual["required"] == 24
    assert annual["available"] == 2
    assert colonial["required"] == 24
    assert colonial["available"] == 2
    assert colonial["status"] == "blocked"
    assert european["required"] == 24
    assert european["available"] == 2
    assert european["status"] == "blocked"


def test_classification_breaks_block_placeholder_artifacts(tmp_path: Path) -> None:
    diagnostics = tmp_path / "results/diagnostics"
    live = tmp_path / "results/live"
    config = tmp_path / "config"
    (diagnostics / "comtrade_product").mkdir(parents=True)
    (diagnostics / "product_industry_mapping").mkdir(parents=True)
    live.mkdir(parents=True)
    config.mkdir(parents=True)

    pd.DataFrame(
        columns=[
            "year",
            "flow_code",
            "classification_code",
            "commodity_code",
            "partner_count",
            "reported_rows",
            "original_classification_rows",
            "estimated_rows",
            "aggregate_rows",
            "trade_value_usd",
            "coverage_status",
        ]
    ).to_csv(diagnostics / "comtrade_product/product_coverage_diagnostics.csv", index=False)
    pd.DataFrame(
        [
            {
                "status": "blocked",
                "max_mapping_coverage_share": 0.0,
                "blocking_reason": "product_industry_mapping_not_registered",
            }
        ]
    ).to_csv(diagnostics / "product_industry_mapping/product_mapping_status.csv", index=False)
    (config / "product_industry_mapping.yml").write_text(
        "\n".join(
            [
                "mapping_version: placeholder",
                "mapping_status: blocked_until_product_level_trade_is_validated",
                "mappings: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (live / "product_industry_mapping_documentation.txt").write_text(
        "Status: blocked\nThe industry panel remains empty until product rows are validated.\n",
        encoding="utf-8",
    )

    audit = build_empirical_readiness_audit(tmp_path)

    classification = audit.loc[audit["requirement"].eq("classification_breaks_documented")].iloc[0]
    assert classification["status"] == "blocked"
    assert "missing or empty" in classification["blocking_reason"]
    assert "product mapping status is blocked" in classification["blocking_reason"]
