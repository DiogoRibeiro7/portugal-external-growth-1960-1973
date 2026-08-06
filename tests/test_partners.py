from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from portugal_external_growth.partners import (
    annotate_comtrade_partner_areas,
    build_requested_partner_return_status,
    configured_comtrade_partner_codes,
    load_comtrade_partner_areas,
    load_historical_group_memberships,
)


def test_configured_comtrade_partner_codes_use_source_area_crosswalk(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "comtrade_partner_areas.yml").write_text(
        """
comtrade_partner_areas:
  - entity_id: france
    entity_label: France
    m49_code: 250
    comtrade_area_code: 251
    comtrade_area_label: France customs area
    start_year: 1962
    end_year: 1973
    mapping_status: customs_area_match
    mapping_source: test
  - entity_id: norway
    entity_label: Norway
    m49_code: 578
    comtrade_area_code: 579
    comtrade_area_label: Norway, Svalbard and Jan Mayen
    start_year: 1962
    end_year: 1973
    mapping_status: customs_area_match
    mapping_source: test
  - entity_id: switzerland_liechtenstein
    entity_label: Switzerland and Liechtenstein
    m49_code: 756
    comtrade_area_code: 757
    comtrade_area_label: Switzerland and Liechtenstein
    start_year: 1962
    end_year: 1973
    mapping_status: customs_area_match
    mapping_source: test
""",
        encoding="utf-8",
    )

    codes = configured_comtrade_partner_codes(tmp_path, (1962,))

    assert codes == (251, 579, 757)
    assert 250 not in codes
    assert 578 not in codes
    assert 756 not in codes


def test_configured_comtrade_partner_codes_falls_back_to_comtrade_config(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "comtrade.yml").write_text(
        """
comtrade:
  partner_codes: [0, 251]
""",
        encoding="utf-8",
    )

    assert configured_comtrade_partner_codes(tmp_path, (1962,)) == (0, 251)


def test_configured_comtrade_partner_codes_rejects_bad_fallback_config(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "comtrade.yml").write_text("comtrade: []\n", encoding="utf-8")

    with pytest.raises(TypeError, match="comtrade.yml is invalid"):
        configured_comtrade_partner_codes(tmp_path, (1962,))


def test_load_comtrade_partner_areas_accepts_empty_list(tmp_path: Path) -> None:
    path = tmp_path / "comtrade_partner_areas.yml"
    path.write_text("comtrade_partner_areas: []\n", encoding="utf-8")

    assert load_comtrade_partner_areas(path).empty


def test_load_comtrade_partner_areas_rejects_missing_list(tmp_path: Path) -> None:
    path = tmp_path / "comtrade_partner_areas.yml"
    path.write_text("comtrade_partner_areas: {}\n", encoding="utf-8")

    with pytest.raises(TypeError, match="comtrade_partner_areas list"):
        load_comtrade_partner_areas(path)


def test_load_historical_group_memberships_expands_entity_to_area_years(tmp_path: Path) -> None:
    _write_area_config(tmp_path)
    groups = tmp_path / "historical_groups.yml"
    groups.write_text(
        """
groups:
  eec_current_membership:
    - {entity_id: france, start_year: 1962, end_year: 1963}
""",
        encoding="utf-8",
    )

    memberships = load_historical_group_memberships(
        groups,
        tmp_path / "comtrade_partner_areas.yml",
    )

    assert memberships[["year", "partner_code", "partner_group"]].to_dict(orient="records") == [
        {"year": 1962, "partner_code": 251, "partner_group": "eec_current_membership"},
        {"year": 1963, "partner_code": 251, "partner_group": "eec_current_membership"},
    ]


def test_load_historical_group_memberships_rejects_bad_groups(tmp_path: Path) -> None:
    _write_area_config(tmp_path)
    groups = tmp_path / "historical_groups.yml"
    groups.write_text("groups: []\n", encoding="utf-8")

    with pytest.raises(TypeError, match="groups mapping"):
        load_historical_group_memberships(groups, tmp_path / "comtrade_partner_areas.yml")


def test_load_historical_group_memberships_ignores_malformed_and_inactive_members(
    tmp_path: Path,
) -> None:
    _write_area_config(tmp_path)
    groups = tmp_path / "historical_groups.yml"
    groups.write_text(
        """
groups:
  ignored_group: {}
  colonies:
    - ignored
    - {entity_id: france, start_year: 1974, end_year: 1975}
""",
        encoding="utf-8",
    )

    assert load_historical_group_memberships(groups, tmp_path / "comtrade_partner_areas.yml").empty


def test_annotate_comtrade_partner_areas_marks_known_and_unknown_codes(tmp_path: Path) -> None:
    _write_area_config(tmp_path)
    frame = pd.DataFrame(
        [
            {"year": 1962, "partner_code": 251, "trade_value_usd": 1.0},
            {"year": 1962, "partner_code": 250, "trade_value_usd": 1.0},
        ]
    )

    result = annotate_comtrade_partner_areas(frame, tmp_path / "comtrade_partner_areas.yml")

    assert result["entity_id"].tolist() == ["france", ""]
    assert result["mapping_status"].tolist() == ["customs_area_match", "unmapped_returned_area"]


def test_annotate_comtrade_partner_areas_is_idempotent(tmp_path: Path) -> None:
    _write_area_config(tmp_path)
    frame = pd.DataFrame([{"year": 1962, "partner_code": 251, "trade_value_usd": 1.0}])

    once = annotate_comtrade_partner_areas(frame, tmp_path / "comtrade_partner_areas.yml")
    twice = annotate_comtrade_partner_areas(once, tmp_path / "comtrade_partner_areas.yml")

    assert twice.columns.tolist().count("entity_id") == 1
    assert twice.loc[0, "entity_id"] == "france"


def test_annotate_comtrade_partner_areas_returns_empty_frame(tmp_path: Path) -> None:
    _write_area_config(tmp_path)

    result = annotate_comtrade_partner_areas(
        pd.DataFrame(),
        tmp_path / "comtrade_partner_areas.yml",
    )

    assert result.empty


def test_requested_partner_status_reports_source_area_not_returned(tmp_path: Path) -> None:
    _write_area_config(tmp_path)
    coverage = pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "classification_code": "S1",
                "partner_code": 0,
            }
        ]
    )

    status = build_requested_partner_return_status(
        coverage,
        tmp_path / "comtrade_partner_areas.yml",
        years=(1962,),
        flows=("X",),
        classification_codes=("S1",),
    )

    france = status.loc[status["entity_id"] == "france"].iloc[0]
    assert not bool(france["returned"])
    assert france["requested_partner_code"] == 251
    assert france["resolution"] == "not_returned_by_api"


def test_load_comtrade_partner_areas_rejects_duplicate_keys(tmp_path: Path) -> None:
    path = tmp_path / "comtrade_partner_areas.yml"
    path.write_text(
        """
comtrade_partner_areas:
  - entity_id: france
    entity_label: France
    m49_code: 250
    comtrade_area_code: 251
    comtrade_area_label: France customs area
    start_year: 1962
    end_year: 1973
    mapping_status: customs_area_match
    mapping_source: test
  - entity_id: france
    entity_label: France
    m49_code: 250
    comtrade_area_code: 251
    comtrade_area_label: France customs area
    start_year: 1962
    end_year: 1973
    mapping_status: customs_area_match
    mapping_source: test
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Duplicate Comtrade partner-area mappings"):
        load_comtrade_partner_areas(path)


def _write_area_config(root: Path) -> None:
    (root / "comtrade_partner_areas.yml").write_text(
        """
comtrade_partner_areas:
  - entity_id: world
    entity_label: World
    m49_code: 0
    comtrade_area_code: 0
    comtrade_area_label: World
    start_year: 1962
    end_year: 1973
    mapping_status: comtrade_total
    mapping_source: test
  - entity_id: france
    entity_label: France
    m49_code: 250
    comtrade_area_code: 251
    comtrade_area_label: France customs area
    start_year: 1962
    end_year: 1973
    mapping_status: customs_area_match
    mapping_source: test
""",
        encoding="utf-8",
    )
