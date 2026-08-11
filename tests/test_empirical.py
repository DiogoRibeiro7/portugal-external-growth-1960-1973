from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from portugal_external_growth.empirical import (
    _reviewed_export_growth_panel,
    build_empirical_prerequisite_status,
    build_empirical_readiness_audit,
    build_empirical_readiness_audit_notes,
    build_empirical_risk_notes,
    build_model_specification_registry,
    build_sectoral_output_growth_panel,
    empty_coefficients,
    empty_design_matrix,
    empty_diagnostics,
    empty_identification_strategy_review,
    empty_sectoral_output_panel,
    load_empirical_design_matrix_or_empty,
)
from portugal_external_growth.io_utils import sha256_file


def test_empirical_prerequisites_are_blocked_by_default() -> None:
    status = build_empirical_prerequisite_status()
    assert set(status["status"]) == {"not_satisfied"}


def test_empirical_coefficients_are_empty() -> None:
    coefficients = empty_coefficients()
    assert coefficients.empty
    assert "estimate" in coefficients.columns


def test_empirical_placeholder_outputs_are_schema_stable() -> None:
    design = empty_design_matrix()
    output_panel = empty_sectoral_output_panel()
    diagnostics = empty_diagnostics()
    specs = build_model_specification_registry()
    notes = build_empirical_risk_notes()

    assert design.empty
    assert "colonial_exposure" in design.columns
    assert "output_growth" in output_panel.columns
    assert diagnostics.loc[0, "status"] == "failed"
    assert set(specs["status"]) == {"blocked_pending_prerequisites"}
    assert "No model has been fit" in notes


def test_empirical_readiness_audit_blocks_empty_repository(tmp_path: Path) -> None:
    audit = build_empirical_readiness_audit(tmp_path)
    notes = build_empirical_readiness_audit_notes(audit)

    assert len(audit) == 35
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
                "world_exports_pte": 100.0 if flow == "X" else None,
                "world_imports_pte": 100.0 if flow == "M" else None,
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
            for industry in [f"sector_{index:02d}" for index in range(10)]
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
        [
            {
                "reconciliation_id": scope,
                "reconciliation_scope": scope,
                "overall_status": "satisfactory_with_caveats",
            }
            for scope in ["ine_comtrade", "cepii", "efta", "oecd"]
        ]
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
    design_rows = [
        {
            "sector_code": f"sector_{sector:02d}",
            "year": year,
            "outcome_variable": "sectoral_output_growth",
            "dependent_variable_value": sector * 0.01 + (year - 1962) * 0.02,
            "dependent_variable_source_file": "data/processed/live/sectoral_output_panel.csv",
            "dependent_variable_source_column": "output_growth",
            "colonial_exposure": (
                sector * 0.02 + (year - 1962) * 0.01 + sector * (year - 1962) * 0.001
            ),
            "european_exposure": (
                sector * 0.03 - (year - 1962) * 0.005 + (sector**2) * (year - 1962) * 0.0001
            ),
            "controls_available": True,
            "source_id": "test_source",
            "source_quality": "reviewed",
        }
        for sector in range(10)
        for year in range(1962, 1974)
    ]
    pd.DataFrame(design_rows).to_csv(interim / "empirical_design_matrix.csv", index=False)
    _write_reviewed_output_panel(tmp_path, design_rows)
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
    assert "sectoral_output_source_registry" in satisfied
    assert "sectoral_output_source_coverage" in satisfied
    assert "real_output_coverage" in satisfied
    assert "output_growth_coverage" in satisfied
    assert "price_deflator_coverage" in satisfied
    assert "outcome_source_provenance" in satisfied
    assert "outcome_definition_consistency" in satisfied
    assert "territorial_consistency" in satisfied
    assert "cross_source_reconciliation" in satisfied
    assert "usable_industries" in satisfied
    assert "usable_years" in satisfied
    assert "usable_growth_years" in satisfied
    assert "classification_breaks_documented" in satisfied
    assert "dependent_variable_coverage" in satisfied
    assert "identification_variables_available" in satisfied
    assert "within_sector_exposure_variation" in satisfied
    assert "within_year_cross_sectional_variation" in satisfied
    assert "fixed_effect_residual_design_rank" in satisfied
    assert "observation_parameter_ratio" in satisfied
    assert "sector_year_uniqueness" in satisfied
    assert "sector_year_grid_coverage" in satisfied
    assert "minimum_sector_years_per_industry" in satisfied
    assert "residual_degrees_of_freedom" in satisfied
    assert "independent_cluster_count" in satisfied
    residual_df = audit.loc[audit["requirement"].eq("residual_degrees_of_freedom")].iloc[0]
    assert residual_df["available"] == 88

    blocked_model_registry = build_model_specification_registry(tmp_path)
    fixed_effects_blocked = blocked_model_registry.loc[
        blocked_model_registry["model_slug"].eq("sector_year_fixed_effects")
    ].iloc[0]
    assert fixed_effects_blocked["status"] == "blocked_pending_prerequisites"
    assert (
        "simultaneity_and_common_shock_strategy" in fixed_effects_blocked["blocking_requirements"]
    )

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

    model_registry = build_model_specification_registry(tmp_path)
    fixed_effects = model_registry.loc[
        model_registry["model_slug"].eq("sector_year_fixed_effects")
    ].iloc[0]
    efta = model_registry.loc[model_registry["model_slug"].eq("efta_tariff_exposure")].iloc[0]
    colonial = model_registry.loc[model_registry["model_slug"].eq("colonial_demand_shifters")].iloc[
        0
    ]
    assert fixed_effects["status"] == "ready"
    assert efta["status"] == "blocked_pending_prerequisites"
    assert "efta_policy_tariff_data_availability" in efta["blocking_requirements"]
    assert colonial["status"] == "blocked_pending_prerequisites"
    assert "external_demand_shifter_availability" in colonial["blocking_requirements"]


def test_empirical_design_matrix_loader_preserves_existing_matrix(tmp_path: Path) -> None:
    path = tmp_path / "data/interim/live"
    path.mkdir(parents=True)
    existing = pd.DataFrame(
        [
            {
                "year": 1962,
                "sector_code": "textiles",
                "outcome_variable": "sectoral_output_growth",
                "dependent_variable_value": 0.03,
                "dependent_variable_source_file": ("data/processed/live/sectoral_output_panel.csv"),
                "dependent_variable_source_column": "output_growth",
                "colonial_exposure": 0.2,
                "european_exposure": 0.3,
                "controls_available": True,
                "source_id": "test_source",
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


def test_sectoral_output_readiness_requires_actual_output_panel(tmp_path: Path) -> None:
    live = tmp_path / "results/live"
    live.mkdir(parents=True)
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

    audit = build_empirical_readiness_audit(tmp_path)

    sectoral = audit.loc[audit["requirement"].eq("sectoral_output_source_coverage")].iloc[0]
    deflator = audit.loc[audit["requirement"].eq("price_deflator_coverage")].iloc[0]
    assert sectoral["status"] == "blocked"
    assert deflator["status"] == "blocked"
    assert "sectoral output panel" in sectoral["blocking_reason"]
    assert "sectoral output panel" in deflator["blocking_reason"]


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
    pd.DataFrame(
        [
            {
                "reconciliation_id": "ine_comtrade_1962",
                "reconciliation_scope": "ine_comtrade",
                "overall_status": "satisfactory_with_caveats",
            }
        ]
    ).to_csv(
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
    assert industries["required"] == 10
    assert industries["available"] == 1
    assert industries["status"] == "blocked"


def test_trade_sample_years_are_loaded_from_project_config(tmp_path: Path) -> None:
    config = tmp_path / "config"
    processed = tmp_path / "data/processed/live"
    config.mkdir(parents=True)
    processed.mkdir(parents=True)
    (config / "project.yml").write_text(
        "\n".join(
            [
                "project:",
                "  bilateral_trade_panel_start_year: 1962",
                "  bilateral_trade_panel_end_year: 1963",
                "",
            ]
        ),
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "year": year,
                "flow_code": flow,
                "world_exports_pte": 100.0 if flow == "X" else None,
                "world_imports_pte": 100.0 if flow == "M" else None,
            }
            for year in [1962, 1963, 1964]
            for flow in ["X", "M"]
        ]
    ).to_csv(processed / "validated_annual_aggregate_external_orientation.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    annual = audit.loc[audit["requirement"].eq("annual_trade_coverage")].iloc[0]
    assert annual["required"] == 4
    assert annual["available"] == 4
    assert annual["status"] == "satisfied"


def test_annual_trade_coverage_requires_non_null_trade_values(tmp_path: Path) -> None:
    processed = tmp_path / "data/processed/live"
    processed.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "year": year,
                "flow_code": flow,
                "world_exports_pte": None,
                "world_imports_pte": None,
            }
            for year in range(1962, 1974)
            for flow in ["X", "M"]
        ]
    ).to_csv(processed / "validated_annual_aggregate_external_orientation.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    annual = audit.loc[audit["requirement"].eq("annual_trade_coverage")].iloc[0]
    assert annual["required"] == 24
    assert annual["available"] == 0
    assert annual["status"] == "blocked"


def test_identification_checks_reject_year_effect_absorbed_exposures(tmp_path: Path) -> None:
    interim = tmp_path / "data/interim/live"
    interim.mkdir(parents=True)
    rows = [
        {
            "sector_code": f"sector_{sector:02d}",
            "year": year,
            "outcome_variable": "sectoral_output_growth",
            "dependent_variable_value": (year - 1962) * 0.01,
            "dependent_variable_source_file": "data/processed/live/sectoral_output_panel.csv",
            "dependent_variable_source_column": "output_growth",
            "colonial_exposure": 0.2 + (year - 1962) * 0.01,
            "european_exposure": 0.4 - (year - 1962) * 0.01,
            "controls_available": True,
            "source_id": "test_source",
            "source_quality": "reviewed",
        }
        for sector in range(10)
        for year in range(1962, 1974)
    ]
    pd.DataFrame(rows).to_csv(interim / "empirical_design_matrix.csv", index=False)
    _write_reviewed_output_panel(tmp_path, rows)

    audit = build_empirical_readiness_audit(tmp_path)

    identification = audit.loc[audit["requirement"].eq("identification_variables_available")].iloc[
        0
    ]
    within_sector = audit.loc[audit["requirement"].eq("within_sector_exposure_variation")].iloc[0]
    within_year = audit.loc[audit["requirement"].eq("within_year_cross_sectional_variation")].iloc[
        0
    ]
    residual_rank = audit.loc[audit["requirement"].eq("fixed_effect_residual_design_rank")].iloc[0]
    assert identification["status"] == "satisfied"
    assert within_sector["status"] == "satisfied"
    assert within_year["available"] == 0
    assert within_year["status"] == "blocked"
    assert residual_rank["available"] == 0
    assert residual_rank["status"] == "blocked"


def test_empirical_design_matrix_requires_numeric_dependent_variable(tmp_path: Path) -> None:
    interim = tmp_path / "data/interim/live"
    interim.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "sector_code": f"sector_{sector:02d}",
                "year": year,
                "colonial_exposure": (
                    sector * 0.02 + (year - 1962) * 0.01 + sector * (year - 1962) * 0.001
                ),
                "european_exposure": (
                    sector * 0.03 - (year - 1962) * 0.005 + (sector**2) * (year - 1962) * 0.0001
                ),
                "controls_available": True,
            }
            for sector in range(10)
            for year in range(1962, 1974)
        ]
    ).to_csv(interim / "empirical_design_matrix.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    dependent = audit.loc[audit["requirement"].eq("dependent_variable_coverage")].iloc[0]
    identification = audit.loc[audit["requirement"].eq("identification_variables_available")].iloc[
        0
    ]
    assert dependent["available"] == 0
    assert dependent["status"] == "blocked"
    assert identification["status"] == "satisfied"


def test_outcome_readiness_rejects_unreviewed_arbitrary_dependent_values(
    tmp_path: Path,
) -> None:
    processed = tmp_path / "data/processed/live"
    interim = tmp_path / "data/interim/live"
    processed.mkdir(parents=True)
    interim.mkdir(parents=True)
    sectors = [f"sector_{sector:02d}" for sector in range(10)]
    pd.DataFrame(
        [
            {
                "sector_code": sector,
                "year": year,
                "source_classification": "unreviewed_classification",
                "source_sector_code": sector,
                "harmonised_sector_code": sector,
                "classification_version": "unknown",
                "mapping_version": "unknown",
                "nominal_output": 100.0,
                "real_output": None,
                "output_growth": None,
                "deflator": 1.0,
                "unit": "unknown",
                "currency": "PTE",
                "price_basis": "nominal",
                "deflator_base": "unknown",
                "classification_break_status": "unreviewed",
                "source_id": "",
                "source_quality": "unreviewed",
            }
            for sector in sectors
            for year in range(1962, 1974)
        ]
    ).to_csv(processed / "sectoral_output_panel.csv", index=False)
    pd.DataFrame(
        [
            {
                "sector_code": sector,
                "year": year,
                "outcome_variable": "random_number",
                "dependent_variable_value": sector_index * 100 + year,
                "dependent_variable_source_file": "data/processed/live/sectoral_output_panel.csv",
                "dependent_variable_source_column": "output_growth",
                "colonial_exposure": sector_index * 0.02 + (year - 1962) * 0.01,
                "european_exposure": sector_index * 0.03 + (year - 1962) * 0.02,
                "controls_available": True,
                "source_id": "",
                "source_quality": "unreviewed",
            }
            for sector_index, sector in enumerate(sectors)
            for year in range(1962, 1974)
        ]
    ).to_csv(interim / "empirical_design_matrix.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)
    prerequisites = build_empirical_prerequisite_status(tmp_path)

    blocked = {
        row["requirement"]: row
        for row in audit.loc[audit["status"].eq("blocked")].to_dict(orient="records")
    }
    assert blocked["output_growth_coverage"]["available"] == 0
    assert blocked["outcome_source_provenance"]["available"] == 0
    assert blocked["outcome_definition_consistency"]["available"] == 0
    assert blocked["dependent_variable_coverage"]["available"] == 0
    sectoral_prerequisite = prerequisites.loc[
        prerequisites["prerequisite"].eq("portuguese_sectoral_output_data")
    ].iloc[0]
    assert sectoral_prerequisite["status"] == "not_satisfied"


def test_outcome_readiness_requires_source_id_to_resolve_in_registry(tmp_path: Path) -> None:
    interim = tmp_path / "data/interim/live"
    interim.mkdir(parents=True)
    rows = [
        {
            "sector_code": f"sector_{sector:02d}",
            "year": year,
            "outcome_variable": "sectoral_output_growth",
            "dependent_variable_value": sector * 0.01 + (year - 1962) * 0.02,
            "dependent_variable_source_file": "data/processed/live/sectoral_output_panel.csv",
            "dependent_variable_source_column": "output_growth",
            "colonial_exposure": sector * 0.02 + (year - 1962) * 0.01,
            "european_exposure": sector * 0.03 + (year - 1962) * 0.02,
            "controls_available": True,
            "source_id": "made_up_source",
            "source_quality": "reviewed",
        }
        for sector in range(10)
        for year in range(1962, 1974)
    ]
    pd.DataFrame(rows).to_csv(interim / "empirical_design_matrix.csv", index=False)
    _write_reviewed_output_panel(tmp_path, rows)

    audit = build_empirical_readiness_audit(tmp_path)

    provenance = audit.loc[audit["requirement"].eq("outcome_source_provenance")].iloc[0]
    dependent = audit.loc[audit["requirement"].eq("dependent_variable_coverage")].iloc[0]
    assert provenance["available"] == 0
    assert provenance["status"] == "blocked"
    assert dependent["available"] == 0
    assert dependent["status"] == "blocked"


def test_outcome_readiness_requires_authoritative_source_registry(tmp_path: Path) -> None:
    interim = tmp_path / "data/interim/live"
    registry = tmp_path / "data/raw/live/sectoral_output"
    interim.mkdir(parents=True)
    registry.mkdir(parents=True)
    rows = [
        {
            "sector_code": f"sector_{sector:02d}",
            "year": year,
            "outcome_variable": "sectoral_output_growth",
            "dependent_variable_value": sector * 0.01 + (year - 1962) * 0.02,
            "dependent_variable_source_file": "data/processed/live/sectoral_output_panel.csv",
            "dependent_variable_source_column": "output_growth",
            "colonial_exposure": sector * 0.02 + (year - 1962) * 0.01,
            "european_exposure": sector * 0.03 + (year - 1962) * 0.02,
            "controls_available": True,
            "source_id": "fake",
            "source_quality": "reviewed",
        }
        for sector in range(10)
        for year in range(1962, 1974)
    ]
    pd.DataFrame(rows).to_csv(interim / "empirical_design_matrix.csv", index=False)
    _write_reviewed_output_panel(tmp_path, rows)
    pd.DataFrame(
        [
            {
                "source_id": "fake",
                "provider": "",
                "dataset_table": "",
                "source_reference": "",
                "source_file_or_url": "",
                "retrieval_date": "2026-08-10",
                "checksum_if_local": "",
                "years": "1900",
                "classification": "",
                "licence_status": "missing",
                "review_status": "reviewed",
            }
        ]
    ).to_csv(registry / "source_registry.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    registry_row = audit.loc[audit["requirement"].eq("sectoral_output_source_registry")].iloc[0]
    dependent = audit.loc[audit["requirement"].eq("dependent_variable_coverage")].iloc[0]
    assert registry_row["status"] == "blocked"
    assert dependent["available"] == 0
    assert dependent["status"] == "blocked"


def test_outcome_readiness_requires_resolved_classification_breaks(tmp_path: Path) -> None:
    interim = tmp_path / "data/interim/live"
    interim.mkdir(parents=True)
    rows = [
        {
            "sector_code": f"sector_{sector:02d}",
            "year": year,
            "outcome_variable": "sectoral_output_growth",
            "dependent_variable_value": sector * 0.01 + (year - 1962) * 0.02,
            "dependent_variable_source_file": "data/processed/live/sectoral_output_panel.csv",
            "dependent_variable_source_column": "output_growth",
            "colonial_exposure": sector * 0.02 + (year - 1962) * 0.01,
            "european_exposure": sector * 0.03 + (year - 1962) * 0.02,
            "controls_available": True,
            "source_id": "test_source",
            "source_quality": "reviewed",
        }
        for sector in range(10)
        for year in range(1962, 1974)
    ]
    pd.DataFrame(rows).to_csv(interim / "empirical_design_matrix.csv", index=False)
    _write_reviewed_output_panel(tmp_path, rows)
    output_path = tmp_path / "data/processed/live/sectoral_output_panel.csv"
    output = pd.read_csv(output_path)
    output["classification_break_status"] = "unreviewed"
    output["classification_version"] = "unknown"
    output.to_csv(output_path, index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    provenance = audit.loc[audit["requirement"].eq("outcome_source_provenance")].iloc[0]
    definition = audit.loc[audit["requirement"].eq("outcome_definition_consistency")].iloc[0]
    assert provenance["available"] == 0
    assert provenance["status"] == "blocked"
    assert definition["available"] == 0
    assert definition["status"] == "blocked"


def test_outcome_growth_blocks_unbridged_source_transitions(tmp_path: Path) -> None:
    processed = tmp_path / "data/processed/live"
    interim = tmp_path / "data/interim/live"
    registry = tmp_path / "data/raw/live/sectoral_output"
    processed.mkdir(parents=True)
    interim.mkdir(parents=True)
    registry.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "source_id": source_id,
                "provider": "test_provider",
                "dataset_table": "test_table",
                "source_reference": f"test reference {source_id}",
                "source_file_or_url": f"https://example.test/{source_id}.csv",
                "retrieval_date": "2026-08-10",
                "checksum_if_local": "not_applicable",
                "years": "1962-1973",
                "classification": "source_sector_test",
                "licence_status": "test_fixture",
                "review_status": "reviewed",
            }
            for source_id in ["source_a", "source_b"]
        ]
    ).to_csv(registry / "source_registry.csv", index=False)
    design_rows = []
    output_rows = []
    real_output_by_sector: dict[str, float] = {}
    for sector in range(10):
        sector_code = f"sector_{sector:02d}"
        for year in range(1962, 1974):
            growth = sector * 0.01 + (year - 1962) * 0.02
            previous = real_output_by_sector.get(sector_code, 100.0)
            real_output = previous * float(np.exp(growth)) if year > 1962 else previous
            real_output_by_sector[sector_code] = real_output
            source_id = "source_a" if year % 2 == 0 else "source_b"
            design_rows.append(
                {
                    "sector_code": sector_code,
                    "year": year,
                    "outcome_variable": "sectoral_output_growth",
                    "dependent_variable_value": growth,
                    "dependent_variable_source_file": (
                        "data/processed/live/sectoral_output_panel.csv"
                    ),
                    "dependent_variable_source_column": "output_growth",
                    "colonial_exposure": sector * 0.02 + (year - 1962) * 0.01,
                    "european_exposure": sector * 0.03 + (year - 1962) * 0.02,
                    "controls_available": True,
                    "source_id": source_id,
                    "source_quality": "reviewed",
                }
            )
            output_rows.append(
                {
                    "sector_code": sector_code,
                    "year": year,
                    "source_classification": "source_sector_test",
                    "source_sector_code": f"S{sector:02d}",
                    "harmonised_sector_code": sector_code,
                    "classification_version": "test_v1",
                    "mapping_version": "test_mapping_v1",
                    "nominal_output": real_output * 1.1,
                    "real_output": real_output,
                    "output_growth": growth,
                    "deflator": 1.0,
                    "unit": "index",
                    "currency": "PTE",
                    "price_basis": "real",
                    "deflator_base": "1962=1",
                    "classification_break_status": "harmonised",
                    "real_output_method": "source_reported_real",
                    "growth_method": "log_change",
                    "lag_definition": "previous_year",
                    "log_or_percent_change": "log_change",
                    "base_year": "1962",
                    "source_id": source_id,
                    "source_quality": "reviewed",
                }
            )
    pd.DataFrame(design_rows).to_csv(interim / "empirical_design_matrix.csv", index=False)
    pd.DataFrame(output_rows).to_csv(processed / "sectoral_output_panel.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    output_growth = audit.loc[audit["requirement"].eq("output_growth_coverage")].iloc[0]
    dependent = audit.loc[audit["requirement"].eq("dependent_variable_coverage")].iloc[0]
    assert output_growth["available"] == 0
    assert output_growth["status"] == "blocked"
    assert dependent["available"] == 0
    assert dependent["status"] == "blocked"


def test_outcome_growth_blocks_non_trivial_source_link_methods(tmp_path: Path) -> None:
    processed = tmp_path / "data/processed/live"
    interim = tmp_path / "data/interim/live"
    registry = tmp_path / "data/raw/live/sectoral_output"
    transitions = tmp_path / "results/diagnostics/sectoral_output"
    processed.mkdir(parents=True)
    interim.mkdir(parents=True)
    registry.mkdir(parents=True)
    transitions.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "source_id": source_id,
                "provider": "test_provider",
                "dataset_table": "test_table",
                "source_reference": f"test reference {source_id}",
                "source_file_or_url": f"https://example.test/{source_id}.csv",
                "retrieval_date": "2026-08-10",
                "checksum_if_local": "not_applicable",
                "years": "1962-1973",
                "classification": "source_sector_test",
                "licence_status": "test_fixture",
                "review_status": "reviewed",
            }
            for source_id in ["source_a", "source_b"]
        ]
    ).to_csv(registry / "source_registry.csv", index=False)
    pd.DataFrame(
        [
            {
                "from_source_id": "source_a",
                "to_source_id": "source_b",
                "sector_code": "sector_00",
                "transition_year": 1963,
                "unit_consistent": True,
                "classification_consistent": True,
                "price_basis_consistent": True,
                "level_link_method": "ratio_linked",
                "status": "reconciled",
                "notes": "non-trivial link method is not implemented",
            }
        ]
    ).to_csv(transitions / "source_transition_registry.csv", index=False)
    growth = float(np.log(2.0))
    pd.DataFrame(
        [
            {
                "sector_code": "sector_00",
                "year": 1963,
                "outcome_variable": "sectoral_output_growth",
                "dependent_variable_value": growth,
                "dependent_variable_source_file": "data/processed/live/sectoral_output_panel.csv",
                "dependent_variable_source_column": "output_growth",
                "colonial_exposure": 0.2,
                "european_exposure": 0.3,
                "controls_available": True,
                "source_id": "source_b",
                "source_quality": "reviewed",
            }
        ]
    ).to_csv(interim / "empirical_design_matrix.csv", index=False)
    pd.DataFrame(
        [
            _sectoral_output_row("sector_00", 1962, 100.0, 0.0, source_id="source_a"),
            _sectoral_output_row("sector_00", 1963, 200.0, growth, source_id="source_b"),
        ]
    ).to_csv(processed / "sectoral_output_panel.csv", index=False)

    growth_panel = build_sectoral_output_growth_panel(tmp_path)

    assert growth_panel.empty


def test_outcome_readiness_controls_real_output_method(tmp_path: Path) -> None:
    interim = tmp_path / "data/interim/live"
    interim.mkdir(parents=True)
    rows = [
        {
            "sector_code": f"sector_{sector:02d}",
            "year": year,
            "outcome_variable": "sectoral_output_growth",
            "dependent_variable_value": sector * 0.01 + (year - 1962) * 0.02,
            "dependent_variable_source_file": "data/processed/live/sectoral_output_panel.csv",
            "dependent_variable_source_column": "output_growth",
            "colonial_exposure": sector * 0.02 + (year - 1962) * 0.01,
            "european_exposure": sector * 0.03 + (year - 1962) * 0.02,
            "controls_available": True,
            "source_id": "test_source",
            "source_quality": "reviewed",
        }
        for sector in range(10)
        for year in range(1962, 1974)
    ]
    pd.DataFrame(rows).to_csv(interim / "empirical_design_matrix.csv", index=False)
    _write_reviewed_output_panel(tmp_path, rows)
    output_path = tmp_path / "data/processed/live/sectoral_output_panel.csv"
    output = pd.read_csv(output_path)
    output["real_output_method"] = "banana_method"
    output.to_csv(output_path, index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    provenance = audit.loc[audit["requirement"].eq("outcome_source_provenance")].iloc[0]
    dependent = audit.loc[audit["requirement"].eq("dependent_variable_coverage")].iloc[0]
    assert provenance["available"] == 0
    assert dependent["available"] == 0


def test_outcome_readiness_checks_deflated_nominal_arithmetic(tmp_path: Path) -> None:
    interim = tmp_path / "data/interim/live"
    interim.mkdir(parents=True)
    rows = [
        {
            "sector_code": f"sector_{sector:02d}",
            "year": year,
            "outcome_variable": "sectoral_output_growth",
            "dependent_variable_value": sector * 0.01 + (year - 1962) * 0.02,
            "dependent_variable_source_file": "data/processed/live/sectoral_output_panel.csv",
            "dependent_variable_source_column": "output_growth",
            "colonial_exposure": sector * 0.02 + (year - 1962) * 0.01,
            "european_exposure": sector * 0.03 + (year - 1962) * 0.02,
            "controls_available": True,
            "source_id": "test_source",
            "source_quality": "reviewed",
        }
        for sector in range(10)
        for year in range(1962, 1974)
    ]
    pd.DataFrame(rows).to_csv(interim / "empirical_design_matrix.csv", index=False)
    _write_reviewed_output_panel(tmp_path, rows)
    output_path = tmp_path / "data/processed/live/sectoral_output_panel.csv"
    output = pd.read_csv(output_path)
    output["real_output_method"] = "deflated_nominal"
    output["nominal_output"] = 1000.0
    output["deflator"] = 999.0
    output.to_csv(output_path, index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    output_growth = audit.loc[audit["requirement"].eq("output_growth_coverage")].iloc[0]
    assert output_growth["available"] == 0
    assert output_growth["status"] == "blocked"


def test_materialised_output_growth_must_match_recomputed_lineage(tmp_path: Path) -> None:
    interim = tmp_path / "data/interim/live"
    processed = tmp_path / "data/processed/live"
    interim.mkdir(parents=True)
    rows = [
        {
            "sector_code": f"sector_{sector:02d}",
            "year": year,
            "outcome_variable": "sectoral_output_growth",
            "dependent_variable_value": sector * 0.01 + (year - 1962) * 0.02,
            "dependent_variable_source_file": "data/processed/live/sectoral_output_panel.csv",
            "dependent_variable_source_column": "output_growth",
            "colonial_exposure": sector * 0.02 + (year - 1962) * 0.01,
            "european_exposure": sector * 0.03 + (year - 1962) * 0.02,
            "controls_available": True,
            "source_id": "test_source",
            "source_quality": "reviewed",
        }
        for sector in range(10)
        for year in range(1962, 1974)
    ]
    pd.DataFrame(rows).to_csv(interim / "empirical_design_matrix.csv", index=False)
    _write_reviewed_output_panel(tmp_path, rows)
    growth = build_sectoral_output_growth_panel(tmp_path)
    growth.loc[growth["year"].eq(1963), "output_growth"] = 999.0
    growth.to_csv(processed / "sectoral_output_growth_panel.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    output_growth = audit.loc[audit["requirement"].eq("output_growth_coverage")].iloc[0]
    dependent = audit.loc[audit["requirement"].eq("dependent_variable_coverage")].iloc[0]
    assert output_growth["available"] == 0
    assert dependent["available"] == 0


def test_output_growth_rejects_duplicate_sector_year_levels(tmp_path: Path) -> None:
    processed = tmp_path / "data/processed/live"
    registry = tmp_path / "data/raw/live/sectoral_output"
    processed.mkdir(parents=True)
    registry.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "source_id": "test_source",
                "provider": "test_provider",
                "dataset_table": "test_table",
                "source_reference": "test reference",
                "source_file_or_url": "https://example.test/test_source.csv",
                "retrieval_date": "2026-08-10",
                "checksum_if_local": "not_applicable",
                "years": "1962-1973",
                "classification": "source_sector_test",
                "licence_status": "test_fixture",
                "review_status": "reviewed",
            }
        ]
    ).to_csv(registry / "source_registry.csv", index=False)
    growth = float(np.log(220.0 / 200.0))
    pd.DataFrame(
        [
            _sectoral_output_row("sector_00", 1962, 100.0, 0.0),
            _sectoral_output_row("sector_00", 1962, 200.0, 0.0),
            _sectoral_output_row("sector_00", 1963, 220.0, growth),
        ]
    ).to_csv(processed / "sectoral_output_panel.csv", index=False)

    growth_panel = build_sectoral_output_growth_panel(tmp_path)
    audit = build_empirical_readiness_audit(tmp_path)

    requirement = "sectoral_output_sector_year_uniqueness"
    uniqueness = audit.loc[audit["requirement"].eq(requirement)].iloc[0]
    assert growth_panel.empty
    assert uniqueness["available"] == 0
    assert uniqueness["status"] == "blocked"
    assert "duplicate analytical sector-year levels" in uniqueness["blocking_reason"]


def test_unique_sector_year_levels_keep_derived_output_growth(tmp_path: Path) -> None:
    processed = tmp_path / "data/processed/live"
    registry = tmp_path / "data/raw/live/sectoral_output"
    processed.mkdir(parents=True)
    registry.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "source_id": "test_source",
                "provider": "test_provider",
                "dataset_table": "test_table",
                "source_reference": "test reference",
                "source_file_or_url": "https://example.test/test_source.csv",
                "retrieval_date": "2026-08-10",
                "checksum_if_local": "not_applicable",
                "years": "1962-1973",
                "classification": "source_sector_test",
                "licence_status": "test_fixture",
                "review_status": "reviewed",
            }
        ]
    ).to_csv(registry / "source_registry.csv", index=False)
    growth = float(np.log(220.0 / 200.0))
    pd.DataFrame(
        [
            _sectoral_output_row("sector_00", 1962, 200.0, 0.0),
            _sectoral_output_row("sector_00", 1963, 220.0, growth),
        ]
    ).to_csv(processed / "sectoral_output_panel.csv", index=False)

    growth_panel = build_sectoral_output_growth_panel(tmp_path)
    audit = build_empirical_readiness_audit(tmp_path)

    requirement = "sectoral_output_sector_year_uniqueness"
    uniqueness = audit.loc[audit["requirement"].eq(requirement)].iloc[0]
    assert np.isclose(growth_panel["output_growth"].iloc[0], growth)
    assert uniqueness["status"] == "satisfied"


def test_source_registry_rejects_local_paths_outside_the_repository(tmp_path: Path) -> None:
    external = tmp_path / "external"
    external.mkdir(parents=True)
    external_source = external / "sectoral-output.csv"
    external_source.write_text("sectoral output fixture\n", encoding="utf-8")
    root = tmp_path / "repository"
    registry = root / "data/raw/live/sectoral_output"
    registry.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "source_id": "test_source",
                "provider": "test_provider",
                "dataset_table": "test_table",
                "source_reference": "test reference",
                "source_file_or_url": str(external_source),
                "retrieval_date": "2026-08-10",
                "checksum_if_local": sha256_file(external_source),
                "years": "1962-1973",
                "classification": "source_sector_test",
                "licence_status": "test_fixture",
                "review_status": "reviewed",
            },
            {
                "source_id": "traversal_source",
                "provider": "test_provider",
                "dataset_table": "test_table",
                "source_reference": "test reference",
                "source_file_or_url": "../external/sectoral-output.csv",
                "retrieval_date": "2026-08-10",
                "checksum_if_local": sha256_file(external_source),
                "years": "1962-1973",
                "classification": "source_sector_test",
                "licence_status": "test_fixture",
                "review_status": "reviewed",
            },
        ]
    ).to_csv(registry / "source_registry.csv", index=False)

    audit = build_empirical_readiness_audit(root)

    registry_row = audit.loc[audit["requirement"].eq("sectoral_output_source_registry")].iloc[0]
    assert registry_row["status"] == "blocked"
    assert registry_row["available"] == 0


def test_export_growth_models_require_joined_outcome_exposure_design(tmp_path: Path) -> None:
    processed = tmp_path / "data/processed/live"
    interim = tmp_path / "data/interim/live"
    processed.mkdir(parents=True)
    interim.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "sector_code": f"B{sector}",
                "year": year,
                "outcome_variable": "sectoral_output_growth",
                "dependent_variable_value": 0.01,
                "dependent_variable_source_file": "data/processed/live/sectoral_output_panel.csv",
                "dependent_variable_source_column": "output_growth",
                "colonial_exposure": sector * 0.02 + (year - 1962) * 0.01,
                "european_exposure": sector * 0.03 + (year - 1962) * 0.02,
                "controls_available": True,
                "source_id": "test_source",
                "source_quality": "reviewed",
            }
            for sector in range(10)
            for year in range(1962, 1974)
        ]
    ).to_csv(interim / "empirical_design_matrix.csv", index=False)
    pd.DataFrame(
        [
            {
                "target_industry_code": f"A{sector}",
                "year": year,
                "flow_code": "X",
                "trade_value_usd": 100.0 + sector * 10 + year,
            }
            for sector in range(10)
            for year in range(1962, 1974)
        ]
    ).to_csv(processed / "industry_trade_panel.csv", index=False)

    registry = build_model_specification_registry(tmp_path)

    efta = registry.loc[registry["model_slug"].eq("efta_tariff_exposure")].iloc[0]
    assert efta["status"] == "blocked_pending_prerequisites"
    assert "sectoral_export_growth model design has no joined outcome/exposure sector-years" in str(
        efta["blocking_requirements"]
    )


def test_export_growth_uses_validated_world_total_rows_only(tmp_path: Path) -> None:
    processed = tmp_path / "data/processed/live"
    processed.mkdir(parents=True)
    pd.DataFrame(
        [
            _industry_trade_row("sector_00", 1962, "world_total", 100.0),
            _industry_trade_row("sector_00", 1962, "colonies", 50.0),
            _industry_trade_row("sector_00", 1963, "world_total", 110.0),
            _industry_trade_row("sector_00", 1963, "colonies", 100.0),
        ]
    ).to_csv(processed / "industry_trade_panel.csv", index=False)

    export_growth = _reviewed_export_growth_panel(tmp_path)

    observed = export_growth.loc[export_growth["year"].eq(1963), "sectoral_export_growth"].iloc[0]
    assert np.isclose(observed, np.log(110.0) - np.log(100.0))


def test_export_growth_rejects_unvalidated_industry_trade_rows(tmp_path: Path) -> None:
    processed = tmp_path / "data/processed/live"
    processed.mkdir(parents=True)
    pd.DataFrame(
        [
            _industry_trade_row(
                "sector_00",
                1962,
                "world_total",
                100.0,
                estimate_status="blocked",
                source_quality="blocked",
            ),
            _industry_trade_row(
                "sector_00",
                1963,
                "world_total",
                110.0,
                estimate_status="blocked",
                source_quality="blocked",
            ),
        ]
    ).to_csv(processed / "industry_trade_panel.csv", index=False)

    export_growth = _reviewed_export_growth_panel(tmp_path)

    assert export_growth.empty


def test_source_registry_requires_matching_local_checksum(tmp_path: Path) -> None:
    registry = tmp_path / "data/raw/live/sectoral_output"
    registry.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "source_id": "test_source",
                "provider": "test_provider",
                "dataset_table": "test_table",
                "source_reference": "test reference",
                "source_file_or_url": "data/raw/live/sectoral_output/does-not-exist.csv",
                "retrieval_date": "2026-08-10",
                "checksum_if_local": "deadbeef",
                "years": "1962-1973",
                "classification": "source_sector_test",
                "licence_status": "test_fixture",
                "review_status": "reviewed",
            }
        ]
    ).to_csv(registry / "source_registry.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    registry_row = audit.loc[audit["requirement"].eq("sectoral_output_source_registry")].iloc[0]
    assert registry_row["status"] == "blocked"
    assert registry_row["available"] == 0


def test_source_registry_rejects_file_uri_without_checksum_verification(tmp_path: Path) -> None:
    registry = tmp_path / "data/raw/live/sectoral_output"
    registry.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "source_id": "test_source",
                "provider": "test_provider",
                "dataset_table": "test_table",
                "source_reference": "test reference",
                "source_file_or_url": "file:///tmp/sectoral-output.csv",
                "retrieval_date": "2026-08-10",
                "checksum_if_local": "not_applicable",
                "years": "1962-1973",
                "classification": "source_sector_test",
                "licence_status": "test_fixture",
                "review_status": "reviewed",
            }
        ]
    ).to_csv(registry / "source_registry.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    registry_row = audit.loc[audit["requirement"].eq("sectoral_output_source_registry")].iloc[0]
    assert registry_row["status"] == "blocked"
    assert registry_row["available"] == 0


def test_panel_sufficiency_rejects_sparse_sector_year_grid(tmp_path: Path) -> None:
    interim = tmp_path / "data/interim/live"
    interim.mkdir(parents=True)
    rows = []
    for year_index, year in enumerate(range(1962, 1974)):
        for offset in (0, 5):
            sector = (year_index + offset) % 10
            rows.append(
                {
                    "sector_code": f"sector_{sector:02d}",
                    "year": year,
                    "outcome_variable": "sectoral_output_growth",
                    "dependent_variable_value": sector * 0.01 + year_index * 0.02,
                    "dependent_variable_source_file": (
                        "data/processed/live/sectoral_output_panel.csv"
                    ),
                    "dependent_variable_source_column": "output_growth",
                    "colonial_exposure": (
                        sector * 0.2 + year_index * 0.03 + sector * year_index * 0.01
                    ),
                    "european_exposure": (
                        sector * 0.1
                        + year_index * 0.07
                        + sector * year_index * 0.004
                        + (sector**2) * year_index * 0.005
                    ),
                    "controls_available": True,
                    "source_id": "test_source",
                    "source_quality": "reviewed",
                }
            )
    pd.DataFrame(rows).to_csv(interim / "empirical_design_matrix.csv", index=False)
    _write_reviewed_output_panel(tmp_path, rows)

    audit = build_empirical_readiness_audit(tmp_path)

    satisfied = set(audit.loc[audit["status"].eq("satisfied"), "requirement"])
    assert "identification_variables_available" in satisfied
    assert "within_sector_exposure_variation" in satisfied
    assert "within_year_cross_sectional_variation" in satisfied
    assert "fixed_effect_residual_design_rank" in satisfied
    assert "observation_parameter_ratio" in satisfied
    assert "independent_cluster_count" in satisfied

    grid = audit.loc[audit["requirement"].eq("sector_year_grid_coverage")].iloc[0]
    min_years = audit.loc[audit["requirement"].eq("minimum_sector_years_per_industry")].iloc[0]
    residual_df = audit.loc[audit["requirement"].eq("residual_degrees_of_freedom")].iloc[0]
    assert grid["required"] == 88
    assert grid["available"] == 22
    assert grid["status"] == "blocked"
    assert min_years["available"] < min_years["required"]
    assert min_years["status"] == "blocked"
    assert residual_df["available"] < residual_df["required"]
    assert residual_df["status"] == "blocked"


def test_empirical_readiness_rejects_complete_panel_outside_configured_years(
    tmp_path: Path,
) -> None:
    processed = tmp_path / "data/processed/live"
    interim = tmp_path / "data/interim/live"
    processed.mkdir(parents=True)
    interim.mkdir(parents=True)
    wrong_years = range(1950, 1962)
    sectors = [f"sector_{sector:02d}" for sector in range(10)]
    pd.DataFrame(
        [
            {"target_industry_code": sector, "year": year}
            for sector in sectors
            for year in wrong_years
        ]
    ).to_csv(processed / "industry_trade_panel.csv", index=False)
    pd.DataFrame(
        [
            {
                "sector_code": sector,
                "year": year,
                "dependent_variable_value": sector_index * 0.01 + year_index * 0.02,
                "colonial_exposure": (
                    sector_index * 0.02 + year_index * 0.01 + sector_index * year_index * 0.001
                ),
                "european_exposure": (
                    sector_index * 0.03
                    - year_index * 0.005
                    + (sector_index**2) * year_index * 0.0001
                ),
                "controls_available": True,
            }
            for sector_index, sector in enumerate(sectors)
            for year_index, year in enumerate(wrong_years)
        ]
    ).to_csv(interim / "empirical_design_matrix.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    blocked = {
        row["requirement"]: row
        for row in audit.loc[audit["status"].eq("blocked")].to_dict(orient="records")
    }
    assert blocked["usable_years"]["available"] == 0
    assert blocked["usable_industries"]["available"] == 0
    assert blocked["identification_variables_available"]["available"] == 0
    assert blocked["sector_year_grid_coverage"]["available"] == 0
    assert blocked["residual_degrees_of_freedom"]["available"] == 0


def test_empirical_readiness_rejects_duplicate_sector_year_observations(
    tmp_path: Path,
) -> None:
    interim = tmp_path / "data/interim/live"
    interim.mkdir(parents=True)
    rows = [
        {
            "sector_code": f"sector_{sector:02d}",
            "year": year,
            "outcome_variable": "sectoral_output_growth",
            "dependent_variable_value": sector * 0.01 + (year - 1962) * 0.02,
            "dependent_variable_source_file": "data/processed/live/sectoral_output_panel.csv",
            "dependent_variable_source_column": "output_growth",
            "colonial_exposure": (
                sector * 0.02 + (year - 1962) * 0.01 + sector * (year - 1962) * 0.001
            ),
            "european_exposure": (
                sector * 0.03 - (year - 1962) * 0.005 + (sector**2) * (year - 1962) * 0.0001
            ),
            "controls_available": True,
            "source_id": "test_source",
            "source_quality": "reviewed",
        }
        for sector in range(10)
        for year in range(1962, 1974)
    ]
    rows.append({**rows[10], "colonial_exposure": 0.99})
    pd.DataFrame(rows).to_csv(interim / "empirical_design_matrix.csv", index=False)
    _write_reviewed_output_panel(tmp_path, rows[:-1])

    audit = build_empirical_readiness_audit(tmp_path)

    uniqueness = audit.loc[audit["requirement"].eq("sector_year_uniqueness")].iloc[0]
    assert uniqueness["required"] == 1
    assert uniqueness["available"] == 0
    assert uniqueness["status"] == "blocked"


def test_european_completeness_requires_fixed_partner_sample(tmp_path: Path) -> None:
    processed = tmp_path / "data/processed/live"
    processed.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "year": year,
                "flow_code": flow,
                "efta_participation_exports_pte": 1.0 if flow == "X" else None,
                "efta_participation_imports_pte": 1.0 if flow == "M" else None,
                "eec_membership_exports_pte": None,
                "eec_membership_imports_pte": None,
                "fixed_europe_exports_pte": None,
                "fixed_europe_imports_pte": None,
            }
            for year in range(1962, 1974)
            for flow in ["X", "M"]
        ]
    ).to_csv(processed / "validated_annual_aggregate_external_orientation.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    european = audit.loc[audit["requirement"].eq("european_partner_completeness")].iloc[0]
    assert european["required"] == 24
    assert european["available"] == 0
    assert european["status"] == "blocked"
    assert "fixed European partner-sample" in european["blocking_reason"]


def test_reconciliation_completeness_requires_unique_scopes(tmp_path: Path) -> None:
    diagnostics = tmp_path / "results/diagnostics/reconciliation"
    diagnostics.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "reconciliation_id": f"ine_comtrade_duplicate_{index}",
                "reconciliation_scope": "ine_comtrade",
                "overall_status": "satisfactory_with_caveats",
            }
            for index in range(4)
        ]
    ).to_csv(diagnostics / "reconciliation_registry.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    reconciliation = audit.loc[audit["requirement"].eq("cross_source_reconciliation")].iloc[0]
    assert reconciliation["required"] == 4
    assert reconciliation["available"] == 1
    assert reconciliation["status"] == "blocked"


def _sectoral_output_row(
    sector_code: str,
    year: int,
    real_output: float,
    output_growth: float,
    *,
    source_id: str = "test_source",
) -> dict[str, object]:
    return {
        "sector_code": sector_code,
        "year": year,
        "source_classification": "source_sector_test",
        "source_sector_code": sector_code.replace("sector_", "S"),
        "harmonised_sector_code": sector_code,
        "classification_version": "test_v1",
        "mapping_version": "test_mapping_v1",
        "nominal_output": real_output * 1.1,
        "real_output": real_output,
        "output_growth": output_growth,
        "deflator": 1.0,
        "unit": "index",
        "currency": "PTE",
        "price_basis": "real",
        "deflator_base": "1962=1",
        "classification_break_status": "harmonised",
        "real_output_method": "source_reported_real",
        "growth_method": "log_change",
        "lag_definition": "previous_year",
        "log_or_percent_change": "log_change",
        "base_year": "1962",
        "source_id": source_id,
        "source_quality": "reviewed",
    }


def _industry_trade_row(
    sector_code: str,
    year: int,
    partner_group: str,
    trade_value_usd: float,
    *,
    estimate_status: str = "mapped_observed_product_rows",
    source_quality: str = "product_level_trade_with_registered_industry_mapping",
) -> dict[str, object]:
    return {
        "year": year,
        "flow_code": "X",
        "source_classification": "S1",
        "mapping_scope": "broad",
        "mapping_version": "test_v1",
        "target_industry_code": sector_code,
        "target_industry_group": "test_group",
        "target_industry_label": sector_code,
        "partner_group": partner_group,
        "trade_value_usd": trade_value_usd,
        "product_count": 1,
        "mapping_weight": 1.0,
        "coverage_count": 1,
        "expected_count": 1,
        "coverage_ratio": 1.0,
        "estimate_status": estimate_status,
        "source_quality": source_quality,
    }


def _write_reviewed_output_panel(tmp_path: Path, rows: list[dict[str, object]]) -> None:
    output = tmp_path / "data/processed/live"
    registry = tmp_path / "data/raw/live/sectoral_output"
    output.mkdir(parents=True, exist_ok=True)
    registry.mkdir(parents=True, exist_ok=True)
    source_snapshot = registry / "test.csv"
    source_snapshot.write_text("sectoral output fixture\n", encoding="utf-8")
    pd.DataFrame(
        [
            {
                "source_id": "test_source",
                "provider": "test_provider",
                "dataset_table": "test_table",
                "source_reference": "test reference",
                "source_file_or_url": "data/raw/live/sectoral_output/test.csv",
                "retrieval_date": "2026-08-10",
                "checksum_if_local": sha256_file(source_snapshot),
                "years": "1962-1973",
                "classification": "source_sector_test",
                "licence_status": "test_fixture",
                "review_status": "reviewed",
            }
        ]
    ).to_csv(registry / "source_registry.csv", index=False)
    real_output_by_sector: dict[str, float] = {}
    output_rows = []
    for row in sorted(rows, key=lambda item: (str(item["sector_code"]), int(str(item["year"])))):
        sector = str(row["sector_code"])
        growth = float(str(row["dependent_variable_value"]))
        previous = real_output_by_sector.get(sector, 100.0)
        real_output = (
            previous * float(np.exp(growth)) if sector in real_output_by_sector else previous
        )
        real_output_by_sector[sector] = real_output
        output_rows.append(
            {
                "sector_code": row["sector_code"],
                "year": row["year"],
                "source_classification": "source_sector_test",
                "source_sector_code": str(row["sector_code"]).replace("sector_", "S"),
                "harmonised_sector_code": row["sector_code"],
                "classification_version": "test_v1",
                "mapping_version": "test_mapping_v1",
                "nominal_output": real_output * 1.1,
                "real_output": real_output,
                "output_growth": row["dependent_variable_value"],
                "deflator": 1.0,
                "unit": "index",
                "currency": "PTE",
                "price_basis": "real",
                "deflator_base": "1962=1",
                "classification_break_status": "harmonised",
                "real_output_method": "source_reported_real",
                "growth_method": "log_change",
                "lag_definition": "previous_year",
                "log_or_percent_change": "log_change",
                "base_year": "1962",
                "source_id": row.get("source_id", "test_source"),
                "source_quality": "reviewed",
            }
        )
    pd.DataFrame(output_rows).to_csv(output / "sectoral_output_panel.csv", index=False)


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
    assert european["available"] == 0
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
                "world_exports_pte": 100.0,
                "world_imports_pte": None,
                "colonial_exports_complete_pte": 10.0,
                "colonial_imports_complete_pte": None,
                "efta_participation_exports_pte": 5.0,
                "efta_participation_imports_pte": None,
            },
            {
                "year": 1962,
                "flow_code": "M",
                "world_exports_pte": None,
                "world_imports_pte": 100.0,
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
    assert european["available"] == 0
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
