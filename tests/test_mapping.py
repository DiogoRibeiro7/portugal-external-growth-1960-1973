from __future__ import annotations

from pathlib import Path

import pytest

from portugal_external_growth.mapping import load_sitc_industry_mapping


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
