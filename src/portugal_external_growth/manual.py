"""Templates and validation for manually transcribed historical tables."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd

from portugal_external_growth.config import load_yaml
from portugal_external_growth.io_utils import write_dataframe_with_metadata, write_text_lf

TRADE_TEMPLATE_COLUMNS = [
    "source_id",
    "source_pdf_filename",
    "source_pdf_sha256",
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
    "printed_total_value_source",
    "currency_source",
    "unit_multiplier",
    "cell_status",
    "footnote",
    "transcriber",
    "transcription_date",
    "entry_pass",
    "adjudication_status",
]

AGGREGATE_TEMPLATE_COLUMNS = [
    "source_id",
    "source_pdf_filename",
    "source_pdf_sha256",
    "publication_year",
    "reference_year",
    "table_title",
    "page_number",
    "flow",
    "partner_group_source",
    "series_name_source",
    "value_source",
    "printed_total_value_source",
    "currency_source",
    "unit_source",
    "unit_multiplier",
    "valuation_basis",
    "territorial_definition",
    "cell_status",
    "footnote",
    "transcriber",
    "transcription_date",
    "entry_pass",
    "adjudication_status",
]

AGGREGATE_DISCREPANCY_COLUMNS = [
    "source_id",
    "reference_year",
    "flow",
    "partner_group_source",
    "series_name_source",
    "pass_1_value_source",
    "pass_2_value_source",
    "pass_1_table_title",
    "pass_2_table_title",
    "pass_1_page_number",
    "pass_2_page_number",
    "discrepancy_type",
    "resolution_status",
]

SOURCE_REGISTRY_COLUMNS = [
    "source_id",
    "title_pattern",
    "expected_year",
    "source_pdf_filename",
    "source_pdf_sha256",
    "source_document_status",
    "access_conditions",
    "licence",
    "territorial_definition",
    "notes",
]

DISCREPANCY_COLUMNS = [
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


def prepare_ine_transcription_workflow(root: Path) -> list[Path]:
    """Create controlled INE double-entry transcription workflow files."""

    created = init_ine_transcription(root)
    created.extend(compare_ine_transcriptions(root))
    created.extend(build_ine_harmonised(root))
    return created


def init_ine_transcription(root: Path) -> list[Path]:
    """Create only human-authored INE transcription inputs when missing."""

    source_registry = _build_source_document_registry(root / "config/manual_sources.yml")
    source_registry_path = root / "data/manual/source_documents/source_document_registry.csv"
    _write_if_missing(
        source_registry,
        source_registry_path,
        metadata={"source_files": ["config/manual_sources.yml"], "stage": "source_registry"},
    )

    created = [source_registry_path]
    for pass_number in (1, 2):
        pass_dir = root / f"data/manual/transcriptions/pass_{pass_number}"
        pass_path = pass_dir / f"ine_trade_transcription_pass_{pass_number}.csv"
        frame = pd.DataFrame(columns=TRADE_TEMPLATE_COLUMNS)
        frame["entry_pass"] = pd.Series(dtype="object")
        _write_if_missing(
            frame,
            pass_path,
            metadata={"purpose": f"INE trade double-entry transcription pass {pass_number}"},
        )
        created.append(pass_path)
        aggregate_path = pass_dir / f"ine_aggregate_transcription_pass_{pass_number}.csv"
        aggregate = pd.DataFrame(columns=AGGREGATE_TEMPLATE_COLUMNS)
        aggregate["entry_pass"] = pd.Series(dtype="object")
        _write_if_missing(
            aggregate,
            aggregate_path,
            metadata={"purpose": f"INE aggregate double-entry transcription pass {pass_number}"},
        )
        created.append(aggregate_path)
    return created


def compare_ine_transcriptions(root: Path) -> list[Path]:
    """Regenerate derived INE double-entry discrepancy outputs."""

    discrepancy_path = root / "data/interim/live/ine_transcription_discrepancies.csv"
    pass_1_path = root / "data/manual/transcriptions/pass_1/ine_trade_transcription_pass_1.csv"
    pass_2_path = root / "data/manual/transcriptions/pass_2/ine_trade_transcription_pass_2.csv"
    discrepancies = compare_transcription_passes(
        pass_1_path,
        pass_2_path,
    )
    aggregate_pass_1_path = (
        root / "data/manual/transcriptions/pass_1/ine_aggregate_transcription_pass_1.csv"
    )
    aggregate_pass_2_path = (
        root / "data/manual/transcriptions/pass_2/ine_aggregate_transcription_pass_2.csv"
    )
    aggregate_discrepancy_path = (
        root / "data/interim/live/ine_aggregate_transcription_discrepancies.csv"
    )
    aggregate_discrepancies = compare_aggregate_transcription_passes(
        aggregate_pass_1_path,
        aggregate_pass_2_path,
    )
    write_dataframe_with_metadata(
        discrepancies,
        discrepancy_path,
        metadata={"stage": "ine_double_entry_discrepancy_check"},
        overwrite=True,
    )
    write_dataframe_with_metadata(
        aggregate_discrepancies,
        aggregate_discrepancy_path,
        metadata={"stage": "ine_aggregate_double_entry_discrepancy_check"},
        overwrite=True,
    )
    report_path = root / "results/live/ine_transcription_unresolved.txt"
    write_text_lf(
        report_path,
        _build_ine_transcription_report(
            discrepancies=discrepancies,
            aggregate_discrepancies=aggregate_discrepancies,
            source_registry=_read_optional_csv(
                root / "data/manual/source_documents/source_document_registry.csv",
                SOURCE_REGISTRY_COLUMNS,
            ),
            pass_1=_read_transcription(pass_1_path),
            pass_2=_read_transcription(pass_2_path),
            aggregate_pass_1=_read_aggregate_transcription(aggregate_pass_1_path),
            aggregate_pass_2=_read_aggregate_transcription(aggregate_pass_2_path),
            adjudicated=_read_transcription(
                root / "data/manual/adjudication/ine_trade_adjudicated.csv"
            ),
        ),
    )
    aggregate_report_path = (
        root / "results/diagnostics/historical_sources/ine_1962_aggregate_transcription.txt"
    )
    write_text_lf(
        aggregate_report_path,
        _build_aggregate_transcription_report(
            aggregate_pass_1=_read_aggregate_transcription(aggregate_pass_1_path),
            aggregate_pass_2=_read_aggregate_transcription(aggregate_pass_2_path),
            aggregate_discrepancies=aggregate_discrepancies,
        ),
    )
    return [discrepancy_path, aggregate_discrepancy_path, report_path, aggregate_report_path]


def build_ine_harmonised(root: Path) -> list[Path]:
    """Regenerate derived harmonised outputs from protected adjudication decisions."""

    adjudicated_path = root / "data/manual/adjudication/ine_trade_adjudicated.csv"
    final_path = root / "data/processed/live/ine_trade_harmonised.csv"
    empty_adjudication = pd.DataFrame(columns=TRADE_TEMPLATE_COLUMNS)
    _write_if_missing(
        empty_adjudication,
        adjudicated_path,
        metadata={"stage": "protected_manual_adjudication_decisions"},
    )
    adjudicated = _read_transcription(adjudicated_path)
    write_dataframe_with_metadata(
        adjudicated,
        final_path,
        metadata={
            "source_files": ["data/manual/adjudication/ine_trade_adjudicated.csv"],
            "stage": "harmonised_from_protected_manual_adjudication",
        },
        overwrite=True,
    )
    aggregate_final_path = root / "data/processed/live/ine_1962_aggregate_trade_harmonised.csv"
    aggregate_final = _build_verified_aggregate_harmonised(root)
    write_dataframe_with_metadata(
        aggregate_final,
        aggregate_final_path,
        metadata={
            "source_files": [
                "data/manual/transcriptions/pass_1/ine_aggregate_transcription_pass_1.csv",
                "data/manual/transcriptions/pass_2/ine_aggregate_transcription_pass_2.csv",
                "data/interim/live/ine_aggregate_transcription_discrepancies.csv",
            ],
            "stage": "harmonised_aggregate_from_matching_double_entry",
        },
        overwrite=True,
    )
    return [adjudicated_path, final_path, aggregate_final_path]


def compare_transcription_passes(pass_1_path: Path, pass_2_path: Path) -> pd.DataFrame:
    """Compare two transcription passes and return unresolved discrepancies."""

    pass_1 = _read_transcription(pass_1_path)
    pass_2 = _read_transcription(pass_2_path)
    if pass_1.empty and pass_2.empty:
        return pd.DataFrame(columns=DISCREPANCY_COLUMNS)

    key_columns = [
        "source_id",
        "publication_year",
        "table_title",
        "page_number",
        "flow",
        "partner_name_source",
        "commodity_code_source",
        "commodity_label_source",
    ]
    merged = pass_1.merge(
        pass_2,
        on=key_columns,
        how="outer",
        suffixes=("_pass_1", "_pass_2"),
        indicator=True,
    )
    records: list[dict[str, object]] = []
    for row in merged.to_dict(orient="records"):
        value_1 = row.get("value_source_pass_1")
        value_2 = row.get("value_source_pass_2")
        if row["_merge"] == "both" and _normalise_transcribed_value(
            value_1
        ) == _normalise_transcribed_value(value_2):
            continue
        records.append(
            {
                **{column: row.get(column) for column in key_columns},
                "pass_1_value_source": value_1,
                "pass_2_value_source": value_2,
                "printed_total_value_source": row.get("printed_total_value_source_pass_1")
                or row.get("printed_total_value_source_pass_2"),
                "discrepancy_type": str(row["_merge"]),
                "resolution_status": "requires_adjudication",
            }
        )
    return pd.DataFrame.from_records(records, columns=DISCREPANCY_COLUMNS)


def compare_aggregate_transcription_passes(pass_1_path: Path, pass_2_path: Path) -> pd.DataFrame:
    """Compare two aggregate transcription passes and return unresolved discrepancies."""

    pass_1 = _read_aggregate_transcription(pass_1_path)
    pass_2 = _read_aggregate_transcription(pass_2_path)
    if pass_1.empty and pass_2.empty:
        return pd.DataFrame(columns=AGGREGATE_DISCREPANCY_COLUMNS)

    key_columns = [
        "source_id",
        "reference_year",
        "flow",
        "partner_group_source",
        "series_name_source",
    ]
    merged = pass_1.merge(
        pass_2,
        on=key_columns,
        how="outer",
        suffixes=("_pass_1", "_pass_2"),
        indicator=True,
    )
    records: list[dict[str, object]] = []
    for row in merged.to_dict(orient="records"):
        value_1 = row.get("value_source_pass_1")
        value_2 = row.get("value_source_pass_2")
        if row["_merge"] == "both" and _normalise_transcribed_value(
            value_1
        ) == _normalise_transcribed_value(value_2):
            continue
        records.append(
            {
                **{column: row.get(column) for column in key_columns},
                "pass_1_value_source": value_1,
                "pass_2_value_source": value_2,
                "pass_1_table_title": row.get("table_title_pass_1"),
                "pass_2_table_title": row.get("table_title_pass_2"),
                "pass_1_page_number": row.get("page_number_pass_1"),
                "pass_2_page_number": row.get("page_number_pass_2"),
                "discrepancy_type": str(row["_merge"]),
                "resolution_status": "requires_adjudication",
            }
        )
    return pd.DataFrame.from_records(records, columns=AGGREGATE_DISCREPANCY_COLUMNS)


def _build_verified_aggregate_harmonised(root: Path) -> pd.DataFrame:
    pass_1 = _read_aggregate_transcription(
        root / "data/manual/transcriptions/pass_1/ine_aggregate_transcription_pass_1.csv"
    )
    pass_2 = _read_aggregate_transcription(
        root / "data/manual/transcriptions/pass_2/ine_aggregate_transcription_pass_2.csv"
    )
    if pass_1.empty or pass_2.empty:
        return pd.DataFrame(columns=AGGREGATE_TEMPLATE_COLUMNS)
    key_columns = [
        "source_id",
        "reference_year",
        "flow",
        "partner_group_source",
        "series_name_source",
    ]
    merged = pass_1.merge(
        pass_2,
        on=key_columns,
        how="inner",
        suffixes=("_pass_1", "_pass_2"),
    )
    if merged.empty:
        return pd.DataFrame(columns=AGGREGATE_TEMPLATE_COLUMNS)
    matched = merged.loc[
        merged["value_source_pass_1"].map(_normalise_transcribed_value)
        == merged["value_source_pass_2"].map(_normalise_transcribed_value)
    ]
    if matched.empty:
        return pd.DataFrame(columns=AGGREGATE_TEMPLATE_COLUMNS)
    verified = pd.DataFrame(
        {
            column: (
                matched[column] if column in key_columns else matched.get(f"{column}_pass_1", pd.NA)
            )
            for column in AGGREGATE_TEMPLATE_COLUMNS
        }
    )
    verified["adjudication_status"] = "double_entry_verified"
    return verified.reset_index(drop=True)


def _normalise_transcribed_value(value: Any) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return format(Decimal(text).normalize(), "f")
    except InvalidOperation:
        return text


def _read_transcription(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=TRADE_TEMPLATE_COLUMNS)
    return pd.read_csv(path)


def _read_aggregate_transcription(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=AGGREGATE_TEMPLATE_COLUMNS)
    return pd.read_csv(path)


def _read_optional_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    return pd.read_csv(path)


def _build_ine_transcription_report(
    *,
    discrepancies: pd.DataFrame,
    aggregate_discrepancies: pd.DataFrame,
    source_registry: pd.DataFrame,
    pass_1: pd.DataFrame,
    pass_2: pd.DataFrame,
    aggregate_pass_1: pd.DataFrame,
    aggregate_pass_2: pd.DataFrame,
    adjudicated: pd.DataFrame,
) -> str:
    missing_source_pdfs = _count_blank(source_registry, "source_pdf_filename")
    identified_catalogue_records = _count_equal(
        source_registry,
        "source_document_status",
        "catalogue_record_identified_no_local_pdf",
    )
    missing_pdf_hashes = _count_blank(source_registry, "source_pdf_sha256")
    unreadable_final_cells = _count_equal(adjudicated, "cell_status", "unreadable")
    pending_adjudication = _count_not_in(
        adjudicated,
        "adjudication_status",
        {"", "accepted", "adjudicated", "verified"},
    )
    footnoted_final_rows = _count_nonblank(adjudicated, "footnote")
    verified_aggregate_rows = _verified_aggregate_row_count(
        aggregate_pass_1,
        aggregate_pass_2,
    )
    workflow_status = _ine_workflow_status(
        discrepancies=discrepancies,
        aggregate_discrepancies=aggregate_discrepancies,
        pass_1=pass_1,
        pass_2=pass_2,
        aggregate_pass_1=aggregate_pass_1,
        aggregate_pass_2=aggregate_pass_2,
        adjudicated=adjudicated,
        pending_adjudication=pending_adjudication,
    )
    return "\n".join(
        [
            "INE historical trade transcription status",
            "========================================",
            "",
            f"Registered source-year documents: {len(source_registry)}",
            f"Missing source PDFs: {missing_source_pdfs}",
            f"Catalogue records identified: {identified_catalogue_records}",
            f"Rows without source PDF SHA-256: {missing_pdf_hashes}",
            f"Pass 1 transcribed rows: {len(pass_1)}",
            f"Pass 2 transcribed rows: {len(pass_2)}",
            f"Aggregate pass 1 transcribed rows: {len(aggregate_pass_1)}",
            f"Aggregate pass 2 transcribed rows: {len(aggregate_pass_2)}",
            f"Aggregate double-entry verified rows: {verified_aggregate_rows}",
            f"Workflow status: {workflow_status}",
            f"Unresolved transcription discrepancies: {len(discrepancies)}",
            f"Unresolved aggregate transcription discrepancies: {len(aggregate_discrepancies)}",
            f"Adjudicated final rows: {len(adjudicated)}",
            f"Final rows with unreadable cells: {unreadable_final_cells}",
            f"Final rows pending adjudication: {pending_adjudication}",
            f"Final rows carrying footnotes: {footnoted_final_rows}",
            "",
            "Derived discrepancy outputs are regenerated from the two protected",
            "human-entry passes on every comparison run.",
            "",
        ]
    )


def _verified_aggregate_row_count(
    aggregate_pass_1: pd.DataFrame,
    aggregate_pass_2: pd.DataFrame,
) -> int:
    if aggregate_pass_1.empty or aggregate_pass_2.empty:
        return 0
    key_columns = [
        "source_id",
        "reference_year",
        "flow",
        "partner_group_source",
        "series_name_source",
    ]
    required_columns = [*key_columns, "value_source"]
    if not set(required_columns).issubset(aggregate_pass_1.columns) or not set(
        required_columns
    ).issubset(aggregate_pass_2.columns):
        return 0
    merged = aggregate_pass_1.merge(
        aggregate_pass_2,
        on=key_columns,
        how="inner",
        suffixes=("_pass_1", "_pass_2"),
    )
    if merged.empty:
        return 0
    verified = merged["value_source_pass_1"].map(_normalise_transcribed_value) == merged[
        "value_source_pass_2"
    ].map(_normalise_transcribed_value)
    return int(verified.sum())


def _build_aggregate_transcription_report(
    *,
    aggregate_pass_1: pd.DataFrame,
    aggregate_pass_2: pd.DataFrame,
    aggregate_discrepancies: pd.DataFrame,
) -> str:
    unresolved_years = _format_unique_values(aggregate_discrepancies, "reference_year")
    unresolved_groups = _format_unique_values(aggregate_discrepancies, "partner_group_source")
    return "\n".join(
        [
            "INE aggregate transcription status",
            "==================================",
            "",
            f"Pass 1 aggregate rows: {len(aggregate_pass_1)}",
            f"Pass 2 aggregate rows: {len(aggregate_pass_2)}",
            f"Unresolved aggregate discrepancies: {len(aggregate_discrepancies)}",
            f"Unresolved reference years: {unresolved_years}",
            f"Unresolved partner groups: {unresolved_groups}",
            "",
            "Verified aggregate rows are limited to entries independently keyed in both",
            "protected transcription passes. Remaining discrepancies are pass-1-only queue",
            "rows awaiting independent visual pass-2 verification or controlled aggregation.",
            "",
        ]
    )


def _format_unique_values(frame: pd.DataFrame, column: str) -> str:
    if frame.empty or column not in frame.columns:
        return "none"
    values = sorted({str(value) for value in frame[column].dropna().tolist()})
    return ";".join(values) if values else "none"


def _ine_workflow_status(
    *,
    discrepancies: pd.DataFrame,
    aggregate_discrepancies: pd.DataFrame,
    pass_1: pd.DataFrame,
    pass_2: pd.DataFrame,
    aggregate_pass_1: pd.DataFrame,
    aggregate_pass_2: pd.DataFrame,
    adjudicated: pd.DataFrame,
    pending_adjudication: int,
) -> str:
    if (
        pass_1.empty
        and pass_2.empty
        and aggregate_pass_1.empty
        and aggregate_pass_2.empty
        and adjudicated.empty
    ):
        return "not_started"
    if not discrepancies.empty or not aggregate_discrepancies.empty or pending_adjudication > 0:
        return "in_progress"
    if not pass_1.empty and not pass_2.empty and len(adjudicated) >= max(len(pass_1), len(pass_2)):
        return "complete"
    return "in_progress"


def _count_equal(frame: pd.DataFrame, column: str, value: str) -> int:
    if frame.empty or column not in frame:
        return 0
    return int(frame[column].astype("string").fillna("").eq(value).sum())


def _count_not_in(frame: pd.DataFrame, column: str, values: set[str]) -> int:
    if frame.empty or column not in frame:
        return 0
    normalised = frame[column].astype("string").fillna("").str.strip()
    return int((~normalised.isin(values)).sum())


def _count_blank(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame:
        return 0
    return int(frame[column].astype("string").fillna("").str.strip().eq("").sum())


def _count_nonblank(frame: pd.DataFrame, column: str) -> int:
    if frame.empty or column not in frame:
        return 0
    return int(frame[column].astype("string").fillna("").str.strip().ne("").sum())


def _write_if_missing(
    frame: pd.DataFrame,
    path: Path,
    *,
    metadata: dict[str, object],
) -> None:
    if path.exists():
        return
    write_dataframe_with_metadata(frame, path, metadata=metadata, overwrite=False)


def _build_source_document_registry(config_path: Path) -> pd.DataFrame:
    payload = load_yaml(config_path)
    sources = payload.get("manual_sources")
    if not isinstance(sources, list):
        raise TypeError("manual_sources.yml must contain a manual_sources list")
    records: list[dict[str, object]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        expected_years = source.get("expected_years")
        if not isinstance(expected_years, list):
            continue
        for year in expected_years:
            records.append(
                {
                    "source_id": source["source_id"],
                    "title_pattern": source["title_pattern"],
                    "expected_year": int(year),
                    "source_pdf_filename": "",
                    "source_pdf_sha256": "",
                    "source_document_status": "missing_source_pdf",
                    "access_conditions": "open_document_expected",
                    "licence": "to_be_confirmed_from_source",
                    "territorial_definition": "to_be_transcribed_from_source",
                    "notes": "Register local PDF before transcription.",
                }
            )
    return pd.DataFrame.from_records(records, columns=SOURCE_REGISTRY_COLUMNS)
