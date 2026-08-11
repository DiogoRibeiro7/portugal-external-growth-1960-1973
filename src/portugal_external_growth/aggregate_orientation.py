"""Validated annual aggregate external-orientation outputs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pandas as pd

from portugal_external_growth.config import load_yaml

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
    "fixed_europe_sample_id",
    "fixed_europe_partner_count",
    "efta_export_share",
    "eec_export_share",
    "fixed_europe_export_share",
    "fixed_europe_import_share",
    "non_colonial_world_exports_pte",
    "non_colonial_world_imports_pte",
    "residual_destinations_exports_pte",
    "residual_destinations_imports_pte",
    "residual_destinations_export_share",
    "residual_destinations_import_share",
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
PARTNER_COMPONENT_RECONCILIATION_COLUMNS = [
    "year",
    "flow",
    "component_group",
    "aggregate_value",
    "component_sum",
    "absolute_residual",
    "relative_residual",
    "expected_partner_count",
    "observed_partner_count",
    "status",
    "note",
]
COMPONENT_RESIDUAL_TOLERANCE = 0.001
FIXED_EUROPE_GROUP_NAME = "efta_eec_fixed_partner_sample_ine_benchmark"
FIXED_EUROPE_SERIES_PREFIX = {"M": "imports_from", "X": "exports_to"}
FIXED_EUROPE_SERIES_SUFFIX = "special_trade_current_escudos"


def build_validated_aggregate_orientation_outputs(
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """Build Prompt 07 aggregate orientation outputs from validated inputs only."""

    validated = _read_csv(root / "data/processed/live/ine_aggregate_trade_harmonised.csv")
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

    fixed_sample = fixed_europe_partner_sample(root)
    dataset = _build_dataset(
        validated,
        reconciliation,
        registry,
        pass_1,
        pass_2,
        source_registry,
        fixed_sample=fixed_sample,
    )
    status = _build_status_table(dataset, validated, pass_1, pass_2, source_registry, registry)
    matrix = _build_reconciliation_matrix(validated, reconciliation)
    source_comparison = _build_source_comparison(trade_source_comparison)
    notes = _build_cross_check_notes(dataset, status, matrix, fixed_sample)
    return dataset, status, matrix, source_comparison, notes


def build_ine_partner_component_reconciliation(root: Path) -> pd.DataFrame:
    """Reconcile transcribed INE partner rows against the printed aggregate they belong to."""

    validated = _read_csv(root / "data/processed/live/ine_aggregate_trade_harmonised.csv")
    colonial_members = _ine_ultramar_entities(root)
    europe_members = fixed_europe_partner_sample(root)
    records: list[dict[str, object]] = []
    for year in range(1962, 1974):
        year_rows = _validated_year_rows(validated, year)
        if year_rows.empty:
            continue
        for flow in ("M", "X"):
            records.append(
                _component_record(
                    year_rows,
                    year=year,
                    flow=flow,
                    group="colonial_overseas_territories",
                    members=colonial_members,
                    aggregate=_aggregate_value(year_rows, flow=flow, partner_group="Ultramar"),
                    note=(
                        "Printed Ultramar aggregate compared with the individually printed "
                        "overseas-territory rows transcribed from the same table."
                    ),
                )
            )
            records.append(
                _component_record(
                    year_rows,
                    year=year,
                    flow=flow,
                    group=FIXED_EUROPE_GROUP_NAME,
                    members=europe_members,
                    aggregate=float("nan"),
                    note=(
                        "The source prints no constant-composition European aggregate, so the "
                        "benchmark is the component sum itself and only sample completeness "
                        "can be checked."
                    ),
                )
            )
    return pd.DataFrame.from_records(
        records, columns=PARTNER_COMPONENT_RECONCILIATION_COLUMNS
    ).sort_values(["year", "flow", "component_group"])


def _component_record(
    year_rows: pd.DataFrame,
    *,
    year: int,
    flow: str,
    group: str,
    members: tuple[str, ...] | list[str],
    aggregate: float,
    note: str,
) -> dict[str, object]:
    observed = 0
    component_sum = 0.0
    for entity_id in members:
        value = _member_value(year_rows, flow=flow, entity_id=entity_id)
        if pd.notna(value):
            observed += 1
            component_sum += float(value)
    expected = len(members)
    has_components = observed > 0
    has_aggregate = pd.notna(aggregate)
    residual: float | None = None
    relative: float | None = None
    if has_aggregate and has_components:
        residual = float(aggregate) - component_sum
        relative = residual / float(aggregate) if float(aggregate) else None
    absolute_residual: object = pd.NA if residual is None else residual
    relative_residual: object = pd.NA if relative is None else relative
    if not has_components:
        status = "components_not_transcribed"
    elif not has_aggregate:
        status = "component_sum_only_no_printed_aggregate"
    elif residual == 0:
        status = "exact"
    elif relative is not None and abs(relative) > COMPONENT_RESIDUAL_TOLERANCE:
        status = "residual_exceeds_tolerance"
    else:
        status = "residual_documented"
    if observed < expected and has_components:
        status = f"{status}_incomplete_sample"
    return {
        "year": year,
        "flow": flow,
        "component_group": group,
        "aggregate_value": aggregate if has_aggregate else pd.NA,
        "component_sum": component_sum if has_components else pd.NA,
        "absolute_residual": absolute_residual,
        "relative_residual": relative_residual,
        "expected_partner_count": expected,
        "observed_partner_count": observed,
        "status": status,
        "note": note,
    }


def _member_value(frame: pd.DataFrame, *, flow: str, entity_id: str) -> float:
    if "series_name_source" not in frame.columns:
        return float("nan")
    expected = _fixed_europe_series_name(entity_id, flow=flow)
    if expected is None:
        return float("nan")
    rows = frame.loc[frame["flow"].eq(flow) & frame["series_name_source"].astype(str).eq(expected)]
    if len(rows) != 1:
        return float("nan")
    row = rows.iloc[0]
    return _optional_float(row["value_source"]) * _optional_float(row["unit_multiplier"])


def _ine_ultramar_entities(root: Path) -> tuple[str, ...]:
    """Return the INE overseas-territory entities documented in the committed crosswalk."""

    crosswalk = _read_csv(root / "data/interim/live/historical_colonial_partner_crosswalk.csv")
    required = {"entity_id", "ine_group"}
    if crosswalk.empty or not required.issubset(crosswalk.columns):
        return ()
    ultramar = crosswalk.loc[
        crosswalk["ine_group"].astype("string").str.strip().eq("Ultramar Portugues")
    ]
    return tuple(sorted(set(ultramar["entity_id"].astype(str))))


def _build_dataset(
    validated: pd.DataFrame,
    reconciliation: pd.DataFrame,
    registry: pd.DataFrame,
    pass_1: pd.DataFrame,
    pass_2: pd.DataFrame,
    source_registry: pd.DataFrame,
    *,
    fixed_sample: tuple[str, ...] = (),
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
            _populate_validated_ine_values(
                record,
                year,
                year_validated,
                reconciliation,
                fixed_sample=fixed_sample,
            )
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
    record: dict[str, object],
    year: int,
    year_validated: pd.DataFrame,
    reconciliation: pd.DataFrame,
    *,
    fixed_sample: tuple[str, ...] = (),
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
            "non_colonial_world_exports_pte": world_exports - colonial_exports,
            "non_colonial_world_imports_pte": world_imports - colonial_imports,
            "unassigned_residual_exports_pte": 0.0,
            "unassigned_residual_imports_pte": 0.0,
        }
    )
    _populate_validated_europe_values(
        record,
        year_validated,
        world_exports,
        world_imports,
        fixed_sample=fixed_sample,
    )
    record["valuation_basis"] = _world_metadata_value(year_validated, "valuation_basis")
    record["territorial_definition"] = _world_metadata_value(
        year_validated, "territorial_definition"
    )

    observed_exports = _reconciliation_row(reconciliation, year=year, concept="Overseas exports")
    observed_imports = _reconciliation_row(reconciliation, year=year, concept="Overseas imports")
    world_exports_row = _reconciliation_row(reconciliation, year=year, concept="World exports")
    world_imports_row = _reconciliation_row(reconciliation, year=year, concept="World imports")
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


def _populate_validated_europe_values(
    record: dict[str, object],
    year_validated: pd.DataFrame,
    world_exports: float,
    world_imports: float,
    *,
    fixed_sample: tuple[str, ...] = (),
) -> None:
    efta_exports = _aggregate_value(year_validated, flow="X", partner_group="EFTA")
    efta_imports = _aggregate_value(year_validated, flow="M", partner_group="EFTA")
    eec_exports = _aggregate_value(year_validated, flow="X", partner_group="CEE")
    eec_imports = _aggregate_value(year_validated, flow="M", partner_group="CEE")
    fixed_exports = _fixed_europe_value(year_validated, flow="X", members=fixed_sample)
    fixed_imports = _fixed_europe_value(year_validated, flow="M", members=fixed_sample)
    fixed_observed = pd.notna(fixed_exports) or pd.notna(fixed_imports)
    colonial_exports = _aggregate_value(year_validated, flow="X", partner_group="Ultramar")
    colonial_imports = _aggregate_value(year_validated, flow="M", partner_group="Ultramar")
    residual_exports = world_exports - colonial_exports - fixed_exports
    residual_imports = world_imports - colonial_imports - fixed_imports
    record.update(
        {
            "efta_participation_exports_pte": _optional_value(efta_exports),
            "efta_participation_imports_pte": _optional_value(efta_imports),
            "eec_membership_exports_pte": _optional_value(eec_exports),
            "eec_membership_imports_pte": _optional_value(eec_imports),
            "fixed_europe_exports_pte": _optional_value(fixed_exports),
            "fixed_europe_imports_pte": _optional_value(fixed_imports),
            "fixed_europe_sample_id": FIXED_EUROPE_GROUP_NAME if fixed_observed else pd.NA,
            "fixed_europe_partner_count": len(fixed_sample) if fixed_observed else pd.NA,
            "efta_export_share": _safe_divide(efta_exports, world_exports),
            "eec_export_share": _safe_divide(eec_exports, world_exports),
            "fixed_europe_export_share": _safe_divide(fixed_exports, world_exports),
            "fixed_europe_import_share": _safe_divide(fixed_imports, world_imports),
            "residual_destinations_exports_pte": _optional_value(residual_exports),
            "residual_destinations_imports_pte": _optional_value(residual_imports),
            "residual_destinations_export_share": _safe_divide(residual_exports, world_exports),
            "residual_destinations_import_share": _safe_divide(residual_imports, world_imports),
        }
    )


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
        row = _reconciliation_row(reconciliation, year=1962, concept=concept)
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
    dataset: pd.DataFrame,
    status: pd.DataFrame,
    matrix: pd.DataFrame,
    fixed_sample: tuple[str, ...] = (),
) -> str:
    benchmark_size = len(fixed_sample)
    benchmark_members = ", ".join(fixed_sample) or "no configured members"
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
            "EFTA/EEC variables are populated only from double-entry verified group totals.",
            "",
            "Constant-composition European benchmark",
            "---------------------------------------",
            (
                f"fixed_europe_* values are the sum of {benchmark_size} individually transcribed "
                f"partner rows registered as {FIXED_EUROPE_GROUP_NAME}: "
                f"{benchmark_members}."
            ),
            (
                "They are a fixed-composition benchmark, not total European trade. Finland and "
                "Ireland are excluded because the 1962 and 1965 volumes fold them into the "
                "printed residual 'Outros paises' row, so they cannot be observed on a constant "
                "basis across the benchmark years."
            ),
            (
                "The benchmark is always recomputed from those member rows, and is left missing "
                "for any year in which one member is absent."
            ),
            (
                "residual_destinations_* is the world total minus the colonial aggregate and the "
                "benchmark. It still contains European destinations outside the benchmark, "
                "including Spain, Finland and Ireland."
            ),
            "",
            "Component reconciliation",
            "------------------------",
            (
                "Transcribed partner rows are reconciled against the aggregate printed in the "
                "same table by results/diagnostics/ine_partner_component_reconciliation.csv, "
                "which reports every residual and any incomplete partner sample."
            ),
            "",
        ]
    )


def _world_metadata_value(year_validated: pd.DataFrame, column: str) -> str:
    """Describe a year's source metadata without silently picking one flow's wording.

    A published row covers both flows, so a single arbitrary row's text would misdescribe the
    other flow. Values are taken from the World rows that define the published aggregate, and
    are labelled per flow whenever the source wording differs between them.
    """

    if column not in year_validated.columns:
        return ""
    values: list[tuple[str, str]] = []
    for flow in ("X", "M"):
        rows = _aggregate_rows(year_validated, flow=flow, partner_group="World")
        if rows.empty:
            continue
        text = str(rows.iloc[0].get(column, "")).strip()
        if text:
            values.append((flow, text))
    if not values:
        return ""
    distinct = {text for _flow, text in values}
    if len(distinct) == 1:
        return values[0][1]
    return "; ".join(f"{flow}: {text}" for flow, text in values)


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
    if len(rows) != 1:
        # An ambiguous aggregate must read as missing rather than resolve to an arbitrary row.
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


def _fixed_europe_value(frame: pd.DataFrame, *, flow: str, members: tuple[str, ...]) -> float:
    """Sum reviewed partner rows for the configured fixed sample, or return NaN if incomplete.

    The benchmark is always recomputed from its configured members. A pre-summed row is never
    accepted, because its composition cannot be verified against the configured sample.
    """

    if not members or "series_name_source" not in frame.columns:
        return float("nan")
    flow_rows = frame.loc[frame["flow"].eq(flow)]
    if flow_rows.empty:
        return float("nan")
    series_names = flow_rows["series_name_source"].astype(str)
    total = 0.0
    for entity_id in members:
        expected = _fixed_europe_series_name(entity_id, flow=flow)
        if expected is None:
            return float("nan")
        member_rows = flow_rows.loc[series_names.eq(expected)]
        if len(member_rows) != 1:
            return float("nan")
        member = member_rows.iloc[0]
        value = _optional_float(member["value_source"]) * _optional_float(member["unit_multiplier"])
        if pd.isna(value):
            return float("nan")
        total += value
    return total


def _fixed_europe_series_name(entity_id: str, *, flow: str) -> str | None:
    prefix = FIXED_EUROPE_SERIES_PREFIX.get(flow)
    if prefix is None:
        return None
    return f"{prefix}_{entity_id}_{FIXED_EUROPE_SERIES_SUFFIX}"


def fixed_europe_partner_sample(root: Path) -> tuple[str, ...]:
    """Return the configured fixed European partner sample used for constant-composition shares."""

    group_path = root / "config/historical_groups.yml"
    if not group_path.exists():
        return ()
    payload = load_yaml(group_path)
    groups = payload.get("groups")
    if not isinstance(groups, dict):
        return ()
    members = groups.get(FIXED_EUROPE_GROUP_NAME)
    if not isinstance(members, list):
        return ()
    return tuple(
        str(member["entity_id"])
        for member in members
        if isinstance(member, dict) and member.get("entity_id")
    )


def _reconciliation_row(
    frame: pd.DataFrame,
    *,
    concept: str,
    year: int | None = None,
) -> dict[str, object] | None:
    if frame.empty or "concept" not in frame:
        return None
    rows = frame.loc[frame["concept"].eq(concept)]
    if year is not None:
        year_column = _reconciliation_year_column(rows)
        if year_column is None:
            return None
        rows = rows.loc[pd.to_numeric(rows[year_column], errors="coerce").eq(year)]
    if rows.empty:
        return None
    return cast(dict[str, object], rows.iloc[0].to_dict())


def _reconciliation_year_column(frame: pd.DataFrame) -> str | None:
    for column in ("benchmark_year", "year"):
        if column in frame:
            return column
    return None


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


def _optional_value(value: float) -> object:
    return pd.NA if pd.isna(value) else value


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)
