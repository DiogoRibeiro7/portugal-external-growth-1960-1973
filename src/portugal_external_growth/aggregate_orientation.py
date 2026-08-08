"""Validated annual aggregate external-orientation outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pandas as pd

DATASET_COLUMNS = [
    "year",
    "world_exports_pte",
    "world_imports_pte",
    "colonial_exports_complete_pte",
    "colonial_imports_complete_pte",
    "colonial_exports_observed_comtrade_usd",
    "colonial_imports_observed_comtrade_usd",
    "complete_colonial_export_share",
    "complete_colonial_import_share",
    "observed_colonial_export_share",
    "observed_colonial_import_share",
    "efta_participation_exports_pte",
    "efta_participation_imports_pte",
    "eec_membership_exports_pte",
    "eec_membership_imports_pte",
    "fixed_europe_exports_pte",
    "fixed_europe_imports_pte",
    "efta_export_share",
    "eec_export_share",
    "fixed_europe_export_share",
    "true_rest_of_world_exports_pte",
    "true_rest_of_world_imports_pte",
    "unassigned_residual_exports_pte",
    "unassigned_residual_imports_pte",
    "colonial_observed_partner_count",
    "colonial_expected_partner_count",
    "estimate_status",
    "source_status",
    "reconciliation_status",
    "source_currency",
    "valuation_basis",
    "territorial_definition",
    "notes",
]

STATUS_COLUMNS = [
    "year",
    "source_document_status",
    "aggregate_pass_1_rows",
    "aggregate_pass_2_rows",
    "validated_aggregate_rows",
    "required_validated_rows",
    "source_status",
    "estimate_status",
    "reconciliation_status",
    "blocking_reason",
]

MATRIX_COLUMNS = [
    "year",
    "flow",
    "aggregate_component",
    "preferred_source",
    "preferred_value_pte",
    "comparison_source",
    "comparison_value_usd",
    "comparison_status",
    "coverage_ratio",
    "value_coverage_ratio",
    "use_in_validated_dataset",
    "note",
]

COLONIAL_PARTNER_GROUPS = frozenset({"Ultramar", "Provincias Ultramarinas"})


def build_validated_aggregate_orientation_outputs(
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """Build Prompt 07 aggregate orientation outputs from validated inputs only."""

    validated = _read_csv(root / "data/processed/live/ine_1962_aggregate_trade_harmonised.csv")
    reconciliation = _read_csv(root / "data/interim/live/ine_comtrade_1962_reconciliation.csv")
    registry = _read_csv(root / "results/diagnostics/reconciliation/reconciliation_registry.csv")
    pass_1 = _read_csv(
        root / "data/manual/transcriptions/pass_1/ine_aggregate_transcription_pass_1.csv"
    )
    pass_2 = _read_csv(
        root / "data/manual/transcriptions/pass_2/ine_aggregate_transcription_pass_2.csv"
    )
    source_registry = _read_csv(root / "data/manual/source_documents/source_document_registry.csv")
    trade_source_comparison = _read_csv(root / "data/interim/live/trade_source_comparison.csv")

    dataset = _build_dataset(validated, reconciliation, registry, pass_1, pass_2, source_registry)
    status = _build_status_table(dataset, validated, pass_1, pass_2, source_registry, registry)
    matrix = _build_reconciliation_matrix(validated, reconciliation)
    source_comparison = _build_source_comparison(trade_source_comparison)
    notes = _build_cross_check_notes(dataset, status, matrix)
    return dataset, status, matrix, source_comparison, notes


def _build_dataset(
    validated: pd.DataFrame,
    reconciliation: pd.DataFrame,
    registry: pd.DataFrame,
    pass_1: pd.DataFrame,
    pass_2: pd.DataFrame,
    source_registry: pd.DataFrame,
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    registry_status = _registry_status(registry)
    for year in range(1962, 1974):
        record: dict[str, object] = {column: pd.NA for column in DATASET_COLUMNS}
        record["year"] = year
        record["source_currency"] = "PTE"
        record["reconciliation_status"] = registry_status if year == 1962 else "not_benchmark_year"
        year_validated = _validated_year_rows(validated, year)
        if _has_complete_world_colonial_flows(year_validated):
            _populate_validated_ine_values(record, year_validated, reconciliation)
            record["estimate_status"] = "observed_no_estimation"
            record["source_status"] = "validated_ine_aggregate"
            record["notes"] = (
                "Validated values use double-entry verified INE World and overseas aggregates. "
                "Observed Comtrade colonial shares are retained only as lower-bound diagnostics."
            )
        else:
            p1_rows = _year_count(pass_1, year)
            p2_rows = _year_count(pass_2, year)
            record["estimate_status"] = (
                "blocked_pending_second_pass" if p1_rows > p2_rows else "not_available"
            )
            record["source_status"] = _source_status_for_year(
                source_registry, year, p1_rows, p2_rows
            )
            record["notes"] = _status_note(record["source_status"])
        records.append(record)
    return pd.DataFrame.from_records(records, columns=DATASET_COLUMNS)


def _populate_validated_ine_values(
    record: dict[str, object], year_validated: pd.DataFrame, reconciliation: pd.DataFrame
) -> None:
    world_exports = _aggregate_value(year_validated, flow="X", partner_group="World")
    world_imports = _aggregate_value(year_validated, flow="M", partner_group="World")
    colonial_exports = _aggregate_value(year_validated, flow="X", partner_group="Ultramar")
    colonial_imports = _aggregate_value(year_validated, flow="M", partner_group="Ultramar")
    record.update(
        {
            "world_exports_pte": world_exports,
            "world_imports_pte": world_imports,
            "colonial_exports_complete_pte": colonial_exports,
            "colonial_imports_complete_pte": colonial_imports,
            "complete_colonial_export_share": _safe_divide(colonial_exports, world_exports),
            "complete_colonial_import_share": _safe_divide(colonial_imports, world_imports),
            "true_rest_of_world_exports_pte": world_exports - colonial_exports,
            "true_rest_of_world_imports_pte": world_imports - colonial_imports,
            "unassigned_residual_exports_pte": 0.0,
            "unassigned_residual_imports_pte": 0.0,
        }
    )
    first_row = year_validated.iloc[0]
    record["valuation_basis"] = first_row.get("valuation_basis", "")
    record["territorial_definition"] = first_row.get("territorial_definition", "")

    observed_exports = _reconciliation_row(reconciliation, concept="Overseas exports")
    observed_imports = _reconciliation_row(reconciliation, concept="Overseas imports")
    world_exports_row = _reconciliation_row(reconciliation, concept="World exports")
    world_imports_row = _reconciliation_row(reconciliation, concept="World imports")
    if observed_exports is not None and world_exports_row is not None:
        observed_value = _optional_float(observed_exports.get("source_a_value"))
        world_value = _optional_float(world_exports_row.get("source_a_value"))
        record["colonial_exports_observed_comtrade_usd"] = observed_value
        record["observed_colonial_export_share"] = _safe_divide(observed_value, world_value)
        record["colonial_observed_partner_count"] = observed_exports.get("observed_partner_count")
        record["colonial_expected_partner_count"] = observed_exports.get("expected_partner_count")
    if observed_imports is not None and world_imports_row is not None:
        observed_value = _optional_float(observed_imports.get("source_a_value"))
        world_value = _optional_float(world_imports_row.get("source_a_value"))
        record["colonial_imports_observed_comtrade_usd"] = observed_value
        record["observed_colonial_import_share"] = _safe_divide(observed_value, world_value)


def _build_status_table(
    dataset: pd.DataFrame,
    validated: pd.DataFrame,
    pass_1: pd.DataFrame,
    pass_2: pd.DataFrame,
    source_registry: pd.DataFrame,
    registry: pd.DataFrame,
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    registry_status = _registry_status(registry)
    for raw_row in dataset.to_dict(orient="records"):
        row = {str(key): value for key, value in raw_row.items()}
        year = int(row["year"])
        p1_rows = _year_count(pass_1, year)
        p2_rows = _year_count(pass_2, year)
        validated_rows = _year_count(validated, year)
        records.append(
            {
                "year": year,
                "source_document_status": _source_document_status(source_registry, year),
                "aggregate_pass_1_rows": p1_rows,
                "aggregate_pass_2_rows": p2_rows,
                "validated_aggregate_rows": validated_rows,
                "required_validated_rows": 4,
                "source_status": row["source_status"],
                "estimate_status": row["estimate_status"],
                "reconciliation_status": registry_status if year == 1962 else "not_benchmark_year",
                "blocking_reason": _blocking_reason(row, p1_rows, p2_rows, validated_rows),
            }
        )
    return pd.DataFrame.from_records(records, columns=STATUS_COLUMNS)


def _build_reconciliation_matrix(
    validated: pd.DataFrame, reconciliation: pd.DataFrame
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    component_map = {
        ("X", "World exports"): ("World", "World exports"),
        ("M", "World imports"): ("World", "World imports"),
        ("X", "Overseas exports"): ("Ultramar", "complete colonial exports"),
        ("M", "Overseas imports"): ("Ultramar", "complete colonial imports"),
    }
    for (flow, concept), (partner_group, component) in component_map.items():
        row = _reconciliation_row(reconciliation, concept=concept)
        preferred_value = _aggregate_value(
            _validated_year_rows(validated, 1962), flow=flow, partner_group=partner_group
        )
        records.append(
            {
                "year": 1962,
                "flow": flow,
                "aggregate_component": component,
                "preferred_source": "INE",
                "preferred_value_pte": preferred_value,
                "comparison_source": "UN Comtrade",
                "comparison_value_usd": row.get("source_a_value") if row is not None else pd.NA,
                "comparison_status": row.get("reconciliation_status") if row is not None else "",
                "coverage_ratio": row.get("coverage_ratio") if row is not None else pd.NA,
                "value_coverage_ratio": row.get("value_coverage_ratio")
                if row is not None
                else pd.NA,
                "use_in_validated_dataset": True,
                "note": row.get("explanation") if row is not None else "",
            }
        )
    return pd.DataFrame.from_records(records, columns=MATRIX_COLUMNS)


def _build_source_comparison(trade_source_comparison: pd.DataFrame) -> pd.DataFrame:
    if trade_source_comparison.empty:
        return pd.DataFrame()
    columns = [
        "year",
        "flow_code",
        "source",
        "source_value",
        "source_currency",
        "nominal_conversion_method",
        "coverage_definition",
        "confidence_status",
        "explanatory_note",
    ]
    return trade_source_comparison[
        [column for column in columns if column in trade_source_comparison]
    ]


def _build_cross_check_notes(
    dataset: pd.DataFrame, status: pd.DataFrame, matrix: pd.DataFrame
) -> str:
    share_columns = [
        "complete_colonial_export_share",
        "complete_colonial_import_share",
        "observed_colonial_export_share",
        "observed_colonial_import_share",
        "efta_export_share",
        "eec_export_share",
        "fixed_europe_export_share",
    ]
    share_values = pd.to_numeric(pd.Series(dataset.loc[:, share_columns].stack()), errors="coerce")
    invalid_shares = int(((share_values < 0) | (share_values > 1)).sum())
    validated_years = status.loc[
        status["source_status"].eq("validated_ine_aggregate"), "year"
    ].tolist()
    blocked_years = status.loc[
        status["estimate_status"].eq("blocked_pending_second_pass"), "year"
    ].tolist()
    return "\n".join(
        [
            "Validated annual aggregate external-orientation cross-checks",
            "===========================================================",
            "",
            f"Validated years: {', '.join(str(year) for year in validated_years) or 'none'}",
            (
                "Years blocked by first-pass-only aggregate transcription: "
                f"{', '.join(str(year) for year in blocked_years) or 'none'}"
            ),
            f"Share values outside [0, 1]: {invalid_shares}",
            f"Reconciliation matrix rows: {len(matrix)}",
            "",
            "Complete colonial shares are never filled from incomplete Comtrade colonial rows.",
            "EFTA/EEC variables remain blank until double-entry verified group totals exist.",
            "",
        ]
    )


def _has_complete_world_colonial_flows(frame: pd.DataFrame) -> bool:
    return all(
        not _aggregate_rows(frame, flow=flow, partner_group=partner_group).empty
        for flow, partner_group in (
            ("X", "World"),
            ("M", "World"),
            ("X", "Ultramar"),
            ("M", "Ultramar"),
        )
    )


def _validated_year_rows(frame: pd.DataFrame, year: int) -> pd.DataFrame:
    if frame.empty or "reference_year" not in frame:
        return pd.DataFrame()
    rows = frame.loc[pd.to_numeric(frame["reference_year"], errors="coerce").eq(year)].copy()
    if "adjudication_status" in rows:
        rows = rows.loc[rows["adjudication_status"].eq("double_entry_verified")]
    return rows


def _aggregate_value(frame: pd.DataFrame, *, flow: str, partner_group: str) -> float:
    rows = _aggregate_rows(frame, flow=flow, partner_group=partner_group)
    if rows.empty:
        return float("nan")
    row = rows.iloc[0]
    return _optional_float(row["value_source"]) * _optional_float(row["unit_multiplier"])


def _aggregate_rows(frame: pd.DataFrame, *, flow: str, partner_group: str) -> pd.DataFrame:
    if frame.empty or not {"flow", "partner_group_source"}.issubset(frame.columns):
        return pd.DataFrame()
    partner_groups = frame["partner_group_source"].astype(str)
    if partner_group in COLONIAL_PARTNER_GROUPS:
        partner_mask = partner_groups.isin(COLONIAL_PARTNER_GROUPS)
    else:
        partner_mask = partner_groups.eq(partner_group)
    return frame.loc[frame["flow"].eq(flow) & partner_mask]


def _reconciliation_row(frame: pd.DataFrame, *, concept: str) -> dict[str, object] | None:
    if frame.empty or "concept" not in frame:
        return None
    rows = frame.loc[frame["concept"].eq(concept)]
    if rows.empty:
        return None
    return cast(dict[str, object], rows.iloc[0].to_dict())


def _registry_status(registry: pd.DataFrame) -> str:
    if registry.empty or "overall_status" not in registry:
        return "not_available"
    return str(registry.iloc[0]["overall_status"])


def _source_status_for_year(
    source_registry: pd.DataFrame, year: int, pass_1_rows: int, pass_2_rows: int
) -> str:
    if pass_1_rows > pass_2_rows:
        return "source_registered_pass_1_only"
    status = _source_document_status(source_registry, year)
    if status == "available":
        return "source_registered_pending_transcription"
    return status


def _source_document_status(source_registry: pd.DataFrame, year: int) -> str:
    if source_registry.empty or "expected_year" not in source_registry:
        return "source_registry_missing"
    rows = source_registry.loc[
        pd.to_numeric(source_registry["expected_year"], errors="coerce").eq(year)
    ]
    if rows.empty:
        return "not_registered"
    return str(rows.iloc[0].get("source_document_status", ""))


def _status_note(source_status: object) -> str:
    status = str(source_status)
    if status == "source_registered_pass_1_only":
        return "Aggregate source rows exist only in pass 1 and are not validated."
    if status == "source_registered_pending_transcription":
        return "Source is registered, but validated aggregate transcription is not complete."
    return "No validated source-backed aggregate variables are available for this year."


def _blocking_reason(
    row: dict[str, Any], pass_1_rows: int, pass_2_rows: int, validated_rows: int
) -> str:
    if str(row["source_status"]) == "validated_ine_aggregate":
        return ""
    if pass_1_rows > pass_2_rows:
        return "independent_pass_2_required"
    if validated_rows < 4:
        return "required_validated_world_and_colonial_flows_missing"
    return ""


def _year_count(frame: pd.DataFrame, year: int) -> int:
    if frame.empty or "reference_year" not in frame:
        return 0
    return int(pd.to_numeric(frame["reference_year"], errors="coerce").eq(year).sum())


def _safe_divide(numerator: object, denominator: object) -> object:
    numerator_float = _optional_float(numerator)
    denominator_float = _optional_float(denominator)
    if pd.isna(numerator_float) or pd.isna(denominator_float) or denominator_float == 0:
        return pd.NA
    return numerator_float / denominator_float


def _optional_float(value: object) -> float:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return float(numeric) if pd.notna(numeric) else float("nan")


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)
