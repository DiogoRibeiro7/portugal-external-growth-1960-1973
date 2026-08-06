from __future__ import annotations

import pandas as pd

from portugal_external_growth.descriptive import _build_export_growth_contribution


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
