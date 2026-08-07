from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.manual import (
    AGGREGATE_TEMPLATE_COLUMNS,
    TRADE_TEMPLATE_COLUMNS,
    build_ine_harmonised,
    compare_aggregate_transcription_passes,
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


def test_transcription_pass_comparison_accepts_integer_float_formatting(
    tmp_path: Path,
) -> None:
    pass_1 = tmp_path / "pass_1.csv"
    pass_2 = tmp_path / "pass_2.csv"
    base: dict[str, object] = {column: "" for column in TRADE_TEMPLATE_COLUMNS}
    base.update(
        {
            "source_id": "ine",
            "publication_year": 1962,
            "table_title": "Trade",
            "page_number": 1,
            "flow": "imports",
            "partner_name_source": "World",
            "commodity_code_source": "TOTAL",
            "commodity_label_source": "Total",
        }
    )
    row_1 = {**base, "value_source": "16829535", "entry_pass": "pass_1"}
    row_2 = {**base, "value_source": "16829535.0", "entry_pass": "pass_2"}
    pd.DataFrame([row_1], columns=TRADE_TEMPLATE_COLUMNS).to_csv(pass_1, index=False)
    pd.DataFrame([row_2], columns=TRADE_TEMPLATE_COLUMNS).to_csv(pass_2, index=False)

    result = compare_transcription_passes(pass_1, pass_2)

    assert result.empty


def test_aggregate_transcription_pass_comparison_flags_value_disagreement(
    tmp_path: Path,
) -> None:
    pass_1 = tmp_path / "aggregate_1.csv"
    pass_2 = tmp_path / "aggregate_2.csv"
    base: dict[str, object] = {column: "" for column in AGGREGATE_TEMPLATE_COLUMNS}
    base.update(
        {
            "source_id": "ine",
            "reference_year": 1962,
            "flow": "X",
            "partner_group_source": "World",
            "series_name_source": "total_exports",
            "table_title": "Trade",
            "page_number": 33,
        }
    )
    pd.DataFrame(
        [{**base, "value_source": "10631829", "entry_pass": "pass_1"}],
        columns=AGGREGATE_TEMPLATE_COLUMNS,
    ).to_csv(pass_1, index=False)
    pd.DataFrame(
        [{**base, "value_source": "10631828", "entry_pass": "pass_2"}],
        columns=AGGREGATE_TEMPLATE_COLUMNS,
    ).to_csv(pass_2, index=False)

    result = compare_aggregate_transcription_passes(pass_1, pass_2)

    assert len(result) == 1
    assert result.loc[0, "flow"] == "X"
    assert result.loc[0, "resolution_status"] == "requires_adjudication"


def test_aggregate_transcription_pass_comparison_accepts_integer_float_formatting(
    tmp_path: Path,
) -> None:
    pass_1 = tmp_path / "aggregate_1.csv"
    pass_2 = tmp_path / "aggregate_2.csv"
    base: dict[str, object] = {column: "" for column in AGGREGATE_TEMPLATE_COLUMNS}
    base.update(
        {
            "source_id": "ine",
            "reference_year": 1962,
            "flow": "M",
            "partner_group_source": "World",
            "series_name_source": "total_imports",
        }
    )
    row_1 = {**base, "value_source": "16829535", "entry_pass": "pass_1"}
    row_2 = {**base, "value_source": "16829535.0", "entry_pass": "pass_2"}
    pd.DataFrame([row_1], columns=AGGREGATE_TEMPLATE_COLUMNS).to_csv(pass_1, index=False)
    pd.DataFrame([row_2], columns=AGGREGATE_TEMPLATE_COLUMNS).to_csv(pass_2, index=False)

    result = compare_aggregate_transcription_passes(pass_1, pass_2)

    assert result.empty


def test_aggregate_transcription_pass_comparison_accepts_matching_values(
    tmp_path: Path,
) -> None:
    pass_1 = tmp_path / "aggregate_1.csv"
    pass_2 = tmp_path / "aggregate_2.csv"
    row: dict[str, object] = {column: "" for column in AGGREGATE_TEMPLATE_COLUMNS}
    row.update(
        {
            "source_id": "ine",
            "reference_year": 1962,
            "flow": "M",
            "partner_group_source": "World",
            "series_name_source": "total_imports",
            "value_source": "16829535",
        }
    )
    pd.DataFrame([row], columns=AGGREGATE_TEMPLATE_COLUMNS).to_csv(pass_1, index=False)
    pd.DataFrame([row], columns=AGGREGATE_TEMPLATE_COLUMNS).to_csv(pass_2, index=False)

    result = compare_aggregate_transcription_passes(pass_1, pass_2)

    assert result.empty


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
    row: dict[str, object] = {column: "" for column in TRADE_TEMPLATE_COLUMNS}
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


def test_compare_ine_transcriptions_reports_source_and_adjudication_gaps(
    tmp_path: Path,
) -> None:
    registry_dir = tmp_path / "data/manual/source_documents"
    registry_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "source_id": "ine",
                "title_pattern": "INE",
                "expected_year": 1962,
                "source_pdf_filename": "",
                "source_pdf_sha256": "",
                "source_document_status": "missing_source_pdf",
                "access_conditions": "open",
                "licence": "unknown",
                "territorial_definition": "to_be_transcribed_from_source",
                "notes": "",
            }
        ]
    ).to_csv(registry_dir / "source_document_registry.csv", index=False)
    pass_1 = tmp_path / "data/manual/transcriptions/pass_1"
    pass_2 = tmp_path / "data/manual/transcriptions/pass_2"
    pass_1.mkdir(parents=True)
    pass_2.mkdir(parents=True)
    row: dict[str, object] = {column: "" for column in TRADE_TEMPLATE_COLUMNS}
    row.update(
        {
            "source_id": "ine",
            "publication_year": 1962,
            "table_title": "Trade",
            "page_number": 1,
            "flow": "exports",
            "partner_name_source": "Angola",
            "commodity_code_source": "TOTAL",
            "commodity_label_source": "Total",
            "value_source": "10",
        }
    )
    pd.DataFrame([row], columns=TRADE_TEMPLATE_COLUMNS).to_csv(
        pass_1 / "ine_trade_transcription_pass_1.csv",
        index=False,
    )
    pd.DataFrame([row], columns=TRADE_TEMPLATE_COLUMNS).to_csv(
        pass_2 / "ine_trade_transcription_pass_2.csv",
        index=False,
    )
    adjudication_dir = tmp_path / "data/manual/adjudication"
    adjudication_dir.mkdir(parents=True)
    final_row = {
        **row,
        "cell_status": "unreadable",
        "adjudication_status": "requires_review",
        "footnote": "Illegible source cell",
    }
    pd.DataFrame([final_row], columns=TRADE_TEMPLATE_COLUMNS).to_csv(
        adjudication_dir / "ine_trade_adjudicated.csv",
        index=False,
    )

    compare_ine_transcriptions(tmp_path)

    report = (tmp_path / "results/live/ine_transcription_unresolved.txt").read_text(
        encoding="utf-8"
    )
    assert "Registered source-year documents: 1" in report
    assert "Missing source PDFs: 1" in report
    assert "Catalogue records identified: 0" in report
    assert "Rows without source PDF SHA-256: 1" in report
    assert "Pass 1 transcribed rows: 1" in report
    assert "Pass 2 transcribed rows: 1" in report
    assert "Workflow status: in_progress" in report
    assert "Final rows with unreadable cells: 1" in report
    assert "Final rows pending adjudication: 1" in report
    assert "Final rows carrying footnotes: 1" in report


def test_build_ine_harmonised_preserves_manual_adjudication(tmp_path: Path) -> None:
    adjudication_dir = tmp_path / "data/manual/adjudication"
    adjudication_dir.mkdir(parents=True)
    adjudicated = adjudication_dir / "ine_trade_adjudicated.csv"
    row: dict[str, object] = {column: "" for column in TRADE_TEMPLATE_COLUMNS}
    row.update({"source_id": "ine", "publication_year": 1962, "value_source": "10"})
    pd.DataFrame([row], columns=TRADE_TEMPLATE_COLUMNS).to_csv(adjudicated, index=False)
    original = adjudicated.read_text(encoding="utf-8")

    build_ine_harmonised(tmp_path)

    assert adjudicated.read_text(encoding="utf-8") == original
    final = pd.read_csv(tmp_path / "data/processed/live/ine_trade_harmonised.csv")
    assert final.loc[0, "source_id"] == "ine"


def test_build_ine_harmonised_keeps_verified_aggregate_rows_with_later_gaps(
    tmp_path: Path,
) -> None:
    pass_1_dir = tmp_path / "data/manual/transcriptions/pass_1"
    pass_2_dir = tmp_path / "data/manual/transcriptions/pass_2"
    pass_1_dir.mkdir(parents=True)
    pass_2_dir.mkdir(parents=True)
    verified: dict[str, object] = {column: "" for column in AGGREGATE_TEMPLATE_COLUMNS}
    verified.update(
        {
            "source_id": "ine",
            "reference_year": 1962,
            "flow": "X",
            "partner_group_source": "World",
            "series_name_source": "total_exports",
            "value_source": "10631829",
            "entry_pass": "pass_1",
        }
    )
    one_sided = {
        **verified,
        "reference_year": 1965,
        "value_source": "16572637",
    }
    pd.DataFrame(
        [verified, one_sided],
        columns=AGGREGATE_TEMPLATE_COLUMNS,
    ).to_csv(pass_1_dir / "ine_aggregate_transcription_pass_1.csv", index=False)
    pd.DataFrame(
        [{**verified, "entry_pass": "pass_2"}],
        columns=AGGREGATE_TEMPLATE_COLUMNS,
    ).to_csv(pass_2_dir / "ine_aggregate_transcription_pass_2.csv", index=False)

    build_ine_harmonised(tmp_path)

    final = pd.read_csv(tmp_path / "data/processed/live/ine_1962_aggregate_trade_harmonised.csv")
    assert final["reference_year"].tolist() == [1962]
    assert final.loc[0, "adjudication_status"] == "double_entry_verified"
