from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from portugal_external_growth.product_industry_mapping import (
    build_product_industry_mapping_outputs,
    load_product_industry_mapping,
)


def test_product_industry_mapping_rejects_missing_mapping_list(tmp_path: Path) -> None:
    path = tmp_path / "product_industry_mapping.yml"
    path.write_text("mappings: {}\n", encoding="utf-8")

    with pytest.raises(TypeError, match="mappings list"):
        load_product_industry_mapping(path)


def test_product_industry_mapping_rejects_bad_weight_sum(tmp_path: Path) -> None:
    path = tmp_path / "product_industry_mapping.yml"
    path.write_text(
        """
mapping_version: test_v1
mappings:
  - source_classification: S1
    commodity_code: "001"
    commodity_description: Animals
    target_industry_code: agriculture
    target_industry_group: primary
    target_industry_label: Agriculture
    mapping_scope: broad
    mapping_method: direct_label_match
    mapping_confidence: high
    mapping_weight: 0.5
    evidence_source: fixture
    evidence_reference: table
    notes: test
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="weights must sum to one"):
        load_product_industry_mapping(path)


def test_product_industry_outputs_block_without_product_rows(tmp_path: Path) -> None:
    _write_mapping_config(tmp_path, mappings="")

    mapping, unmapped, coverage, panel, reconciliation, status, notes = (
        build_product_industry_mapping_outputs(tmp_path)
    )

    assert mapping.empty
    assert unmapped.empty
    assert coverage.empty
    assert panel.empty
    assert reconciliation.empty
    assert status.loc[0, "status"] == "blocked"
    assert "product_level_trade_not_validated" in str(status.loc[0, "blocking_reason"])
    assert "Unobserved product records are not interpreted as zero trade" in notes


def test_product_industry_outputs_map_products_and_reconcile(tmp_path: Path) -> None:
    _write_mapping_config(
        tmp_path,
        mappings="""
  - source_classification: S1
    commodity_code: "001"
    commodity_description: Animals
    target_industry_code: agriculture
    target_industry_group: primary
    target_industry_label: Agriculture
    mapping_scope: broad
    mapping_method: direct_label_match
    mapping_confidence: high
    mapping_weight: 1.0
    evidence_source: fixture
    evidence_reference: table
    notes: test
""",
    )
    data_dir = tmp_path / "data/interim/live"
    data_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "classification_code": "S1",
                "commodity_code": "001",
                "commodity_description": "Animals",
                "reporter_code": 620,
                "reporter_desc": "Portugal",
                "partner_code": 24,
                "partner_desc": "Angola",
                "trade_value_usd": 100.0,
                "quantity": pd.NA,
                "quantity_unit_code": pd.NA,
                "quantity_unit_abbr": "",
                "net_weight": pd.NA,
                "gross_weight": pd.NA,
                "is_reported": True,
                "is_original_classification": True,
                "legacy_estimation_flag": 0,
                "is_aggregate": False,
                "aggregate_level": 1,
                "source_file": "fixture.csv",
            }
        ]
    ).to_csv(data_dir / "comtrade_product_normalised.csv", index=False)
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config/partner_groups.yml").write_text(
        """
groups:
  colonies:
    members:
      - {code: 24, name: Angola, start_year: 1960, end_year: 1973}
""",
        encoding="utf-8",
    )
    results = tmp_path / "results/live"
    results.mkdir(parents=True)
    pd.DataFrame([{"status": "ready"}]).to_csv(
        results / "comtrade_product_extraction_status.csv", index=False
    )

    mapping, unmapped, coverage, panel, reconciliation, status, _notes = (
        build_product_industry_mapping_outputs(tmp_path)
    )

    assert len(mapping) == 1
    assert unmapped.empty
    assert coverage.loc[0, "mapping_coverage_share"] == 1.0
    assert panel.loc[0, "partner_group"] == "colonies"
    assert panel.loc[0, "trade_value_usd"] == 100.0
    assert reconciliation.loc[0, "reconciliation_status"] == "reconciles_to_product_total"
    assert status.loc[0, "status"] == "ready"


def _write_mapping_config(root: Path, *, mappings: str) -> None:
    config = root / "config"
    config.mkdir(exist_ok=True)
    mapping_block = mappings if mappings else " []"
    (config / "product_industry_mapping.yml").write_text(
        f"""
mapping_version: test_v1
mapping_status: fixture
mappings:{mapping_block}
""",
        encoding="utf-8",
    )
