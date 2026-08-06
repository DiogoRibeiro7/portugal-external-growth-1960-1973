from __future__ import annotations

import pandas as pd

from portugal_external_growth.validation import validate_trade_shares, validate_unique


def test_validate_unique_reports_duplicates() -> None:
    frame = pd.DataFrame({"year": [1970, 1970], "value": [1, 2]})
    issues = validate_unique(frame, ["year"], name="example")
    assert issues[0].severity == "error"


def test_validate_trade_shares_accepts_complete_groups() -> None:
    frame = pd.DataFrame(
        {
            "year": [1970, 1970],
            "flow_code": ["X", "X"],
            "flow_share": [0.25, 0.75],
        }
    )
    assert validate_trade_shares(frame) == []
