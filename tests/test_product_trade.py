from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.product_trade import (
    build_product_coverage_diagnostics,
    build_product_extraction_design_outputs,
    build_product_extraction_plan,
    build_product_world_reconciliation,
    normalise_product_snapshots,
)


def test_product_extraction_plan_blocks_without_key_or_commodity_batches() -> None:
    plan = build_product_extraction_plan(
        {
            "years": [1962],
            "flow_codes": ["X"],
            "classification_code": "S1",
            "reporter_code": 620,
            "product_extraction": {"partner_codes": [0], "commodity_code_batches": []},
        },
        subscription_key_present=False,
    )

    assert len(plan) == 1
    assert plan.loc[0, "plan_status"] == "blocked"
    blocking_reason = str(plan.loc[0, "blocking_reason"])
    assert "COMTRADE_SUBSCRIPTION_KEY_missing" in blocking_reason
    assert "commodity_code_batches_not_registered" in blocking_reason


def test_product_snapshot_normalisation_and_diagnostics(tmp_path: Path) -> None:
    raw_dir = tmp_path / "data/raw/live/comtrade_product"
    raw_dir.mkdir(parents=True)
    raw = raw_dir / "sample.csv"
    pd.DataFrame(
        [
            {
                "refYear": 1962,
                "flowCode": "X",
                "classificationCode": "S1",
                "cmdCode": "0",
                "cmdDesc": "Food",
                "reporterCode": 620,
                "reporterDesc": "Portugal",
                "partnerCode": 0,
                "partnerDesc": "World",
                "primaryValue": 100.0,
                "qty": 2,
                "qtyUnitCode": 8,
                "qtyUnitAbbr": "kg",
                "netWgt": 2,
                "grossWgt": 3,
                "isReported": True,
                "isOriginalClassification": True,
                "legacyEstimationFlag": 0,
                "isAggregate": False,
                "aggrLevel": 1,
            }
        ]
    ).to_csv(raw, index=False)
    product = normalise_product_snapshots([raw], root=tmp_path)
    coverage = build_product_coverage_diagnostics(product)
    reconciliation = build_product_world_reconciliation(
        product,
        pd.DataFrame(
            [
                {
                    "year": 1962,
                    "flow": "X",
                    "concept": "World exports",
                    "source_a_value": 100.0,
                }
            ]
        ),
    )

    assert product.loc[0, "commodity_description"] == "Food"
    assert coverage.loc[0, "partner_count"] == 1
    assert reconciliation.loc[0, "reconciliation_status"] == "matches_world_total"


def test_product_world_reconciliation_marks_missing_benchmark(tmp_path: Path) -> None:
    raw_dir = tmp_path / "data/raw/live/comtrade_product"
    raw_dir.mkdir(parents=True)
    raw = raw_dir / "sample.csv"
    pd.DataFrame(
        [
            {
                "refYear": 1962,
                "flowCode": "X",
                "classificationCode": "S1",
                "cmdCode": "0",
                "reporterCode": 620,
                "partnerCode": 0,
                "primaryValue": 100.0,
            }
        ]
    ).to_csv(raw, index=False)

    product = normalise_product_snapshots([raw], root=tmp_path)
    reconciliation = build_product_world_reconciliation(product, pd.DataFrame())

    assert reconciliation.loc[0, "reconciliation_status"] == "benchmark_world_value_missing"


def test_product_design_outputs_write_stable_empty_schemas(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "comtrade.yml").write_text(
        """
comtrade:
  years: [1962]
  flow_codes: [X]
  classification_code: S1
  reporter_code: 620
  product_extraction:
    partner_codes: [0]
    commodity_code_batches: []
""",
        encoding="utf-8",
    )

    plan, product, coverage, reconciliation, status, notes = (
        build_product_extraction_design_outputs(tmp_path, subscription_key_present=False)
    )

    assert len(plan) == 1
    assert product.empty
    assert coverage.empty
    assert reconciliation.empty
    assert status.loc[0, "status"] == "blocked"
    assert "subscription final-data endpoint" in notes
