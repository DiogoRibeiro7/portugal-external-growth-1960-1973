from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.manual import TRADE_TEMPLATE_COLUMNS, compare_transcription_passes


def test_transcription_pass_comparison_flags_value_disagreement(tmp_path: Path) -> None:
    pass_1 = tmp_path / "pass_1.csv"
    pass_2 = tmp_path / "pass_2.csv"
    base: dict[str, object] = {column: "" for column in TRADE_TEMPLATE_COLUMNS}
    base.update(
        {
            "source_id": "ine",
            "publication_year": 1962,
            "table_title": "Trade",
            "page_number": 1,
            "flow": "exports",
            "partner_name_source": "Angola",
            "commodity_code_source": "TOTAL",
            "commodity_label_source": "Total",
            "printed_total_value_source": "100",
        }
    )
    row_1 = {**base, "value_source": "10", "entry_pass": "pass_1"}
    row_2 = {**base, "value_source": "11", "entry_pass": "pass_2"}
    pd.DataFrame([row_1], columns=TRADE_TEMPLATE_COLUMNS).to_csv(pass_1, index=False)
    pd.DataFrame([row_2], columns=TRADE_TEMPLATE_COLUMNS).to_csv(pass_2, index=False)

    result = compare_transcription_passes(pass_1, pass_2)

    assert len(result) == 1
    assert result.loc[0, "resolution_status"] == "requires_adjudication"
