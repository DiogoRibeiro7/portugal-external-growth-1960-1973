from __future__ import annotations

import pandas as pd

from portugal_external_growth.descriptive import (
    _build_export_growth_contribution,
    _build_world_denominator_groups,
)

MEMBERSHIPS = pd.DataFrame(
    [
        {"year": 1960, "partner_code": 24, "partner_group": "colonies"},
        {"year": 1962, "partner_code": 24, "partner_group": "colonies"},
        {"year": 1973, "partner_code": 24, "partner_group": "colonies"},
        {"year": 1960, "partner_code": 826, "partner_group": "efta"},
        {"year": 1962, "partner_code": 826, "partner_group": "efta"},
        {"year": 1960, "partner_code": 56, "partner_group": "eec"},
        {"year": 1973, "partner_code": 208, "partner_group": "eec"},
        {"year": 1973, "partner_code": 372, "partner_group": "eec"},
        {"year": 1973, "partner_code": 826, "partner_group": "eec"},
    ]
)


def test_export_growth_contribution_sums_to_one() -> None:
    group_values = pd.DataFrame(
        [
            {"year": 1962, "flow_code": "X", "partner_group": "a", "trade_value_usd": 10.0},
            {"year": 1973, "flow_code": "X", "partner_group": "a", "trade_value_usd": 15.0},
            {"year": 1962, "flow_code": "X", "partner_group": "b", "trade_value_usd": 10.0},
            {"year": 1973, "flow_code": "X", "partner_group": "b", "trade_value_usd": 20.0},
        ]
    )

    result = _build_export_growth_contribution(group_values)

    assert result["contribution_to_export_growth"].sum() == 1.0


def test_preliminary_shares_use_world_denominator_and_true_residual() -> None:
    coverage = pd.DataFrame(
        [
            {"year": 1962, "flow_code": "X", "partner_code": 0, "trade_value_usd": 100.0},
            {"year": 1962, "flow_code": "X", "partner_code": 24, "trade_value_usd": 20.0},
            {"year": 1962, "flow_code": "X", "partner_code": 826, "trade_value_usd": 30.0},
        ]
    )

    result = _build_world_denominator_groups(coverage, MEMBERSHIPS)
    current = result.loc[
        result["classification_scheme"] == "contemporaneous_institutional_membership"
    ]

    assert current["world_share"].sum() == 1.0
    assert current.loc[current["partner_group"] == "colonies", "world_share"].iloc[0] == 0.2
    assert (
        current.loc[current["partner_group"] == "true_rest_of_world", "trade_value_usd"].iloc[0]
        == 50.0
    )


def test_1973_accession_countries_are_current_eec() -> None:
    coverage = pd.DataFrame(
        [
            {"year": 1973, "flow_code": "X", "partner_code": 0, "trade_value_usd": 100.0},
            {"year": 1973, "flow_code": "X", "partner_code": 208, "trade_value_usd": 10.0},
            {"year": 1973, "flow_code": "X", "partner_code": 372, "trade_value_usd": 20.0},
            {"year": 1973, "flow_code": "X", "partner_code": 826, "trade_value_usd": 30.0},
        ]
    )

    result = _build_world_denominator_groups(coverage, MEMBERSHIPS)
    current = result.loc[
        result["classification_scheme"] == "contemporaneous_institutional_membership"
    ]

    assert (
        current.loc[current["partner_group"] == "eec_contemporaneous", "trade_value_usd"].iloc[0]
        == 60.0
    )
