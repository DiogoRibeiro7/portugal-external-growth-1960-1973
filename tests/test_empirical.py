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
        [{"year": year, "flow_code": flow} for year in range(1962, 1974) for flow in ["X", "M"]]
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
        [{"target_industry_code": "agriculture", "year": year} for year in range(1962, 1974)]
    ).to_csv(processed / "industry_trade_panel.csv", index=False)
    pd.DataFrame([{"status": "available"}, {"status": "available"}]).to_csv(
        diagnostics / "industry_exposure/industry_exposure_coverage.csv", index=False
    )
    pd.DataFrame([{"territorial_definition_status": "resolved"}]).to_csv(
        diagnostics / "comtrade_coverage/comtrade_coverage_audit.csv", index=False
    )
    pd.DataFrame([{"overall_status": "reconciled"}]).to_csv(
        diagnostics / "reconciliation/reconciliation_registry.csv", index=False
    )
    pd.DataFrame([{"series": "GDP deflator price", "concept": "sector manufacturing GVA"}]).to_csv(
        live / "bpstat_macro_data_dictionary.csv", index=False
    )
    pd.DataFrame(
        [
            {
                "year": 1962,
                "colonial_exposure": 0.2,
                "european_exposure": 0.3,
                "controls_available": True,
            }
        ]
    ).to_csv(interim / "empirical_design_matrix.csv", index=False)

    audit = build_empirical_readiness_audit(tmp_path)

    satisfied = set(audit.loc[audit["status"].eq("satisfied"), "requirement"])
    assert "annual_trade_coverage" in satisfied
    assert "product_level_coverage" in satisfied
    assert "product_to_industry_mapping_coverage" in satisfied
    assert "usable_years" in satisfied
    assert "identification_variables_available" in satisfied
