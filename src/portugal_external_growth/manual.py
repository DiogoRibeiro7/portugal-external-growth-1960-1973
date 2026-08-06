"""Templates and validation for manually transcribed historical tables."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.io_utils import write_dataframe_with_metadata


TRADE_TEMPLATE_COLUMNS = [
    "source_id",
    "publication_year",
    "table_title",
    "page_number",
    "reporting_territory",
    "flow",
    "partner_name_source",
    "partner_code_harmonised",
    "commodity_code_source",
    "commodity_label_source",
    "value_source",
    "currency_source",
    "unit_multiplier",
    "footnote",
    "transcriber",
    "transcription_date",
    "entry_pass",
]

AGGREGATE_TEMPLATE_COLUMNS = [
    "source_id",
    "publication_year",
    "table_title",
    "page_number",
    "series_name_source",
    "year",
    "value_source",
    "unit_source",
    "territorial_definition",
    "footnote",
    "transcriber",
    "transcription_date",
    "entry_pass",
]


def initialise_templates(root: Path) -> list[Path]:
    """Create empty, schema-stable transcription templates."""

    template_dir = root / "data/manual/templates"
    trade_path = template_dir / "trade_transcription_template.csv"
    aggregate_path = template_dir / "aggregate_cross_check_template.csv"
    write_dataframe_with_metadata(
        pd.DataFrame(columns=TRADE_TEMPLATE_COLUMNS),
        trade_path,
        metadata={"purpose": "Double-entry transcription of historical trade tables"},
    )
    write_dataframe_with_metadata(
        pd.DataFrame(columns=AGGREGATE_TEMPLATE_COLUMNS),
        aggregate_path,
        metadata={"purpose": "Independent aggregate cross-check transcription"},
    )
    return [trade_path, aggregate_path]
