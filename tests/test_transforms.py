from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from portugal_external_growth.transforms import (
    aggregate_trade_orientation,
    classify_partner_groups,
    load_partner_memberships,
    normalise_comtrade,
    summarise_gdp_growth,
)


def test_normalise_comtrade_maps_api_columns() -> None:
    source = pd.DataFrame(
        {
            "period": [1970],
            "reporterCode": [620],
            "partnerCode": [24],
            "partnerDesc": ["Angola"],
            "flowCode": ["X"],
            "cmdCode": ["TOTAL"],
            "primaryValue": [125.0],
        }
    )
    result = normalise_comtrade(source)
    assert result.loc[0, "year"] == 1970
    assert result.loc[0, "trade_value_usd"] == pytest.approx(125.0)
    assert result.loc[0, "partner_desc"] == "Angola"


def test_normalise_comtrade_keeps_partner_descriptions_aligned_after_sort() -> None:
    source = pd.DataFrame(
        {
            "period": [1970, 1970],
            "reporterCode": [620, 620],
            "partnerCode": [826, 24],
            "partnerDesc": ["United Kingdom", "Angola"],
            "flowCode": ["X", "X"],
            "cmdCode": ["TOTAL", "TOTAL"],
            "primaryValue": [30.0, 20.0],
        }
    )

    result = normalise_comtrade(source)

    assert result[["partner_code", "partner_desc"]].to_dict(orient="records") == [
        {"partner_code": 24, "partner_desc": "Angola"},
        {"partner_code": 826, "partner_desc": "United Kingdom"},
    ]


def test_normalise_comtrade_accepts_alias_columns_and_empty_partner_description() -> None:
    source = pd.DataFrame(
        {
            "refYear": [1970],
            "reporterCodeM49": [620],
            "partnerCodeM49": [24],
            "flowCode": ["M"],
            "cmdCode": ["TOTAL"],
            "TradeValue": [50.0],
        }
    )

    result = normalise_comtrade(source)

    assert result.loc[0, "year"] == 1970
    assert result.loc[0, "partner_desc"] == ""
    assert result.loc[0, "trade_value_usd"] == pytest.approx(50.0)


def test_normalise_comtrade_rejects_missing_required_columns() -> None:
    with pytest.raises(ValueError, match="Unable to map required Comtrade column"):
        normalise_comtrade(pd.DataFrame({"period": [1970]}))


def test_normalise_comtrade_empty_frame_returns_stable_schema() -> None:
    result = normalise_comtrade(pd.DataFrame())

    assert result.columns.tolist() == [
        "year",
        "reporter_code",
        "partner_code",
        "partner_desc",
        "flow_code",
        "commodity_code",
        "trade_value_usd",
        "source",
    ]


def test_partner_memberships_rejects_non_mapping_groups(tmp_path: Path) -> None:
    config = tmp_path / "groups.yml"
    config.write_text("groups: []\n", encoding="utf-8")

    with pytest.raises(TypeError, match="groups mapping"):
        load_partner_memberships(config)


def test_partner_memberships_ignores_malformed_entries(tmp_path: Path) -> None:
    config = tmp_path / "groups.yml"
    config.write_text(
        """
        groups:
          malformed_group: ignored
          missing_members: {}
          bad_member:
            members:
              - ignored
          efta:
            members:
              - {code: 826, name: United Kingdom, start_year: 1960, end_year: 1961}
        """,
        encoding="utf-8",
    )

    result = load_partner_memberships(config)

    assert result[["year", "partner_code", "partner_group"]].to_dict(orient="records") == [
        {"year": 1960, "partner_code": 826, "partner_group": "efta"},
        {"year": 1961, "partner_code": 826, "partner_group": "efta"},
    ]


def test_partner_classification_is_time_aware(tmp_path: Path) -> None:
    config = tmp_path / "groups.yml"
    config.write_text(
        """
        groups:
          efta:
            members:
              - {code: 826, name: United Kingdom, start_year: 1960, end_year: 1972}
        """,
        encoding="utf-8",
    )
    trade = pd.DataFrame(
        {
            "year": [1972, 1973],
            "partner_code": [826, 826],
            "flow_code": ["X", "X"],
            "trade_value_usd": [1.0, 1.0],
        }
    )
    memberships = load_partner_memberships(config)
    result = classify_partner_groups(trade, memberships)
    assert result["partner_group"].tolist() == ["efta", "rest_of_world"]


def test_trade_orientation_shares_sum_to_one() -> None:
    classified = pd.DataFrame(
        {
            "year": [1970, 1970],
            "flow_code": ["X", "X"],
            "partner_group": ["colonies", "efta"],
            "trade_value_usd": [25.0, 75.0],
        }
    )
    result = aggregate_trade_orientation(classified)
    assert result["flow_share"].sum() == pytest.approx(1.0)


def test_trade_orientation_empty_frame_returns_stable_schema() -> None:
    result = aggregate_trade_orientation(pd.DataFrame())

    assert result.columns.tolist() == [
        "year",
        "flow_code",
        "partner_group",
        "trade_value_usd",
        "flow_share",
    ]


def test_gdp_summary_compounds_growth() -> None:
    source = pd.DataFrame({"year": [1961, 1962], "value": [10.0, 10.0]})
    result = summarise_gdp_growth(source)
    assert result.loc[0, "cumulative_real_gdp_index_start_100"] == pytest.approx(121.0)


def test_gdp_summary_rejects_missing_columns() -> None:
    with pytest.raises(ValueError, match="GDP input is missing required columns"):
        summarise_gdp_growth(pd.DataFrame({"year": [1961]}))
