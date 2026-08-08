from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.industry_exposure import (
    build_export_growth_decomposition,
    build_group_composition,
    build_industry_exposure_outputs,
    build_industry_exposure_panel,
)


def test_industry_exposure_outputs_block_without_industry_panel(tmp_path: Path) -> None:
    results = tmp_path / "results/diagnostics/product_industry_mapping"
    results.mkdir(parents=True)
    pd.DataFrame([{"status": "blocked"}]).to_csv(
        results / "product_mapping_status.csv", index=False
    )

    exposures, composition, growth, coverage, status, notes = build_industry_exposure_outputs(
        tmp_path
    )

    assert exposures.empty
    assert composition.empty
    assert growth.empty
    assert coverage.loc[0, "status"] == "blocked"
    assert status.loc[0, "status"] == "blocked"
    assert "industry_trade_panel_empty" in str(status.loc[0, "blocking_reason"])
    assert "No causal claims" in notes


def test_industry_exposure_panel_calculates_descriptive_shares() -> None:
    panel = _industry_panel()

    exposures = build_industry_exposure_panel(panel)

    row = exposures.loc[exposures["year"].eq(1962)].iloc[0]
    assert row["total_exports_usd"] == 200.0
    assert row["colonial_exports_usd"] == 50.0
    assert row["european_exports_usd"] == 70.0
    assert row["colonial_exposure"] == 0.25
    assert row["european_exposure"] == 0.35
    assert row["estimate_status"] == "descriptive_observed_world_denominator"


def test_industry_group_composition_and_growth_decomposition() -> None:
    panel = _industry_panel()

    composition = build_group_composition(panel)
    growth = build_export_growth_decomposition(panel)

    world_1962 = composition.loc[
        composition["partner_group"].eq("world_total") & composition["year"].eq(1962)
    ].iloc[0]
    assert world_1962["industry_share_within_group"] == 1.0
    world_growth = growth.loc[growth["partner_group"].eq("world_total")].iloc[0]
    assert world_growth["export_growth_usd"] == 100.0
    assert world_growth["contribution_to_group_export_growth"] == 1.0
    assert world_growth["estimate_status"] == "descriptive_endpoint_growth"


def _industry_panel() -> pd.DataFrame:
    base = {
        "flow_code": "X",
        "source_classification": "S1",
        "mapping_scope": "broad",
        "mapping_version": "test_v1",
        "target_industry_code": "agriculture",
        "target_industry_group": "primary",
        "target_industry_label": "Agriculture",
        "product_count": 1,
        "mapping_weight": 1.0,
        "coverage_count": 1,
        "expected_count": 1,
        "coverage_ratio": 1.0,
        "estimate_status": "mapped_observed_product_rows",
        "source_quality": "fixture",
    }
    rows: list[dict[str, object]] = []
    for year, world, colonies, europe in [(1962, 200.0, 50.0, 70.0), (1973, 300.0, 90.0, 80.0)]:
        rows.extend(
            [
                {**base, "year": year, "partner_group": "world_total", "trade_value_usd": world},
                {**base, "year": year, "partner_group": "colonies", "trade_value_usd": colonies},
                {
                    **base,
                    "year": year,
                    "partner_group": "efta_participation",
                    "trade_value_usd": europe,
                },
            ]
        )
    return pd.DataFrame.from_records(rows)
