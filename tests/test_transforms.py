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
            "flowCode": ["X"],
            "cmdCode": ["TOTAL"],
            "primaryValue": [125.0],
        }
    )
    result = normalise_comtrade(source)
    assert result.loc[0, "year"] == 1970
    assert result.loc[0, "trade_value_usd"] == pytest.approx(125.0)


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


def test_gdp_summary_compounds_growth() -> None:
    source = pd.DataFrame({"year": [1961, 1962], "value": [10.0, 10.0]})
    result = summarise_gdp_growth(source)
    assert result.loc[0, "cumulative_real_gdp_index_start_100"] == pytest.approx(121.0)
