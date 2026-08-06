from __future__ import annotations

import pandas as pd

from portugal_external_growth.reconciliation import finalise_trade_reconciliation


def test_reconciliation_keeps_conflicting_source_values() -> None:
    comparison = pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "source": "UN Comtrade",
                "source_value": 100.0,
                "benchmark_source": "UN Comtrade",
            },
            {
                "year": 1962,
                "flow_code": "X",
                "source": "INE",
                "source_value": 90.0,
                "benchmark_source": "UN Comtrade",
            },
        ]
    )

    result = finalise_trade_reconciliation(comparison)

    assert result.loc[result["source"] == "INE", "source_value"].iloc[0] == 90.0
    assert result.loc[result["source"] == "INE", "difference_from_benchmark"].iloc[0] == -10.0
