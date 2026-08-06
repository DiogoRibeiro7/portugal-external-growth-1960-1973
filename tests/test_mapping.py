from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from portugal_external_growth.mapping import build_mapping_outputs, load_sitc_industry_mapping


def test_sitc_mapping_rejects_bad_weight_sums(tmp_path: Path) -> None:
    path = tmp_path / "mapping.yml"
    path.write_text(
        """
mappings:
  - classification_revision: SITC Rev.1
    commodity_code_source: "001"
    industry_code: A
    industry_label: A
    mapping_scope: broad
    weight: 0.5
    decision_source: manual
    decision_note: test
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="weights must sum to one"):
        load_sitc_industry_mapping(path)


def test_sitc_mapping_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "mapping.yml"
    path.write_text(
        """
mappings:
  - classification_revision: SITC Rev.1
    commodity_code_source: "001"
    industry_code: A
    industry_label: A
    mapping_scope: broad
    weight: 0.5
    decision_source: manual
    decision_note: test
  - classification_revision: SITC Rev.1
    commodity_code_source: "001"
    industry_code: A
    industry_label: A
    mapping_scope: broad
    weight: 0.5
    decision_source: manual
    decision_note: test
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate SITC mapping keys"):
        load_sitc_industry_mapping(path)


def test_mapping_coverage_is_calculated_by_classification_revision(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "sitc_industry_mapping.yml").write_text(
        """
classification_revision: SITC Rev.1
mapping_status: pending_official_correspondence
mappings: []
""",
        encoding="utf-8",
    )
    coverage_dir = tmp_path / "data/interim/live"
    coverage_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "classification_code": "S1",
                "commodity_code_source": "TOTAL",
                "trade_value_usd": 100.0,
            },
            {
                "classification_code": "S2",
                "commodity_code_source": "TOTAL",
                "trade_value_usd": 200.0,
            },
        ]
    ).to_csv(coverage_dir / "comtrade_coverage_matrix.csv", index=False)

    _, unmapped, coverage, _, _ = build_mapping_outputs(tmp_path)

    assert coverage["classification_code"].tolist() == ["S1", "S2"]
    assert coverage["total_trade_value_usd"].tolist() == [100.0, 200.0]
    assert unmapped["classification_revision"].tolist() == ["SITC Rev.1", "SITC Rev.2"]
