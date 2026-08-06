from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.manual import (
    AGGREGATE_TEMPLATE_COLUMNS,
    TRADE_TEMPLATE_COLUMNS,
    compare_ine_transcriptions,
    compare_transcription_passes,
    initialise_templates,
    prepare_ine_transcription_workflow,
)


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


def test_initialise_templates_writes_trade_and_aggregate_schemas(tmp_path: Path) -> None:
    paths = initialise_templates(tmp_path)

    trade = pd.read_csv(paths[0])
    aggregate = pd.read_csv(paths[1])
    assert trade.columns.tolist() == TRADE_TEMPLATE_COLUMNS
    assert aggregate.columns.tolist() == AGGREGATE_TEMPLATE_COLUMNS


def test_transcription_pass_comparison_handles_missing_inputs(tmp_path: Path) -> None:
    result = compare_transcription_passes(tmp_path / "missing_1.csv", tmp_path / "missing_2.csv")

    assert result.empty
    assert result.columns.tolist() == [
        "source_id",
        "publication_year",
        "table_title",
        "page_number",
        "flow",
        "partner_name_source",
        "commodity_code_source",
        "commodity_label_source",
        "pass_1_value_source",
        "pass_2_value_source",
        "printed_total_value_source",
        "discrepancy_type",
        "resolution_status",
    ]


def test_prepare_ine_transcription_does_not_overwrite_pass_files(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "manual_sources.yml").write_text(
        """
manual_sources:
  - source_id: ine
    title_pattern: INE
    expected_years: [1962]
    target_template: data/manual/templates/trade_transcription_template.csv
    validation: double_entry
""",
        encoding="utf-8",
    )
    pass_dir = tmp_path / "data/manual/transcriptions/pass_1"
    pass_dir.mkdir(parents=True)
    pass_file = pass_dir / "ine_trade_transcription_pass_1.csv"
    row = {column: "" for column in TRADE_TEMPLATE_COLUMNS}
    row["source_id"] = "human_entered"
    pd.DataFrame([row], columns=TRADE_TEMPLATE_COLUMNS).to_csv(pass_file, index=False)
    original = pass_file.read_text(encoding="utf-8")

    prepare_ine_transcription_workflow(tmp_path)

    assert pass_file.read_text(encoding="utf-8") == original


def test_compare_ine_transcriptions_regenerates_stale_discrepancy_file(tmp_path: Path) -> None:
    pass_1 = tmp_path / "data/manual/transcriptions/pass_1"
    pass_2 = tmp_path / "data/manual/transcriptions/pass_2"
    pass_1.mkdir(parents=True)
    pass_2.mkdir(parents=True)
    stale = tmp_path / "data/interim/live/ine_transcription_discrepancies.csv"
    stale.parent.mkdir(parents=True)
    pd.DataFrame(columns=["old"]).to_csv(stale, index=False)
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
        }
    )
    pd.DataFrame([{**base, "value_source": "10"}], columns=TRADE_TEMPLATE_COLUMNS).to_csv(
        pass_1 / "ine_trade_transcription_pass_1.csv",
        index=False,
    )
    pd.DataFrame([{**base, "value_source": "11"}], columns=TRADE_TEMPLATE_COLUMNS).to_csv(
        pass_2 / "ine_trade_transcription_pass_2.csv",
        index=False,
    )

    compare_ine_transcriptions(tmp_path)

    regenerated = pd.read_csv(stale)
    assert regenerated["resolution_status"].tolist() == ["requires_adjudication"]
