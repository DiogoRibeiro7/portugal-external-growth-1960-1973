"""Normalisation and aggregation transformations."""

from __future__ import annotations

from pathlib import Path
from statistics import fmean, median

import pandas as pd

from portugal_external_growth.config import load_yaml

COMTRADE_COLUMN_CANDIDATES: dict[str, tuple[str, ...]] = {
    "year": ("period", "refYear"),
    "reporter_code": ("reporterCode", "reporterCodeM49"),
    "partner_code": ("partnerCode", "partnerCodeM49"),
    "partner_desc": ("partnerDesc", "partnerDescM49"),
    "flow_code": ("flowCode",),
    "commodity_code": ("cmdCode",),
    "trade_value_usd": ("primaryValue", "TradeValue", "tradeValue"),
    "cif_value_usd": ("cifvalue", "CIFValue", "cifValue"),
    "fob_value_usd": ("fobvalue", "FOBValue", "fobValue"),
    "is_reported": ("isReported",),
    "is_original_classification": ("isOriginalClassification",),
    "legacy_estimation_flag": ("legacyEstimationFlag",),
}

OPTIONAL_COMTRADE_COLUMNS = {
    "cif_value_usd",
    "fob_value_usd",
    "is_reported",
    "is_original_classification",
    "legacy_estimation_flag",
}

TERRITORIAL_DEFINITION_COLUMNS = [
    "source_key",
    "reporter_code",
    "year",
    "status",
    "definition",
    "evidence_count",
    "evidence_summary",
]


def _select_column(frame: pd.DataFrame, candidates: tuple[str, ...], target: str) -> pd.Series:
    for candidate in candidates:
        if candidate in frame.columns:
            return frame[candidate]
    if target == "partner_desc":
        return pd.Series([""] * len(frame), index=frame.index, dtype="string")
    if target in OPTIONAL_COMTRADE_COLUMNS:
        return pd.Series([pd.NA] * len(frame), index=frame.index, dtype="object")
    raise ValueError(f"Unable to map required Comtrade column '{target}' from {candidates}")


def normalise_comtrade(frame: pd.DataFrame) -> pd.DataFrame:
    """Convert source-specific Comtrade columns to a stable schema."""

    if frame.empty:
        return pd.DataFrame(columns=[*COMTRADE_COLUMN_CANDIDATES, "source"])
    output = pd.DataFrame(
        {
            target: _select_column(frame, candidates, target)
            for target, candidates in COMTRADE_COLUMN_CANDIDATES.items()
        }
    )
    for column in ("year", "reporter_code", "partner_code"):
        output[column] = pd.to_numeric(output[column], errors="raise").astype("int64")
    for column in ("trade_value_usd", "cif_value_usd", "fob_value_usd"):
        output[column] = pd.to_numeric(output[column], errors="coerce")
    output["partner_desc"] = output["partner_desc"].astype("string")
    output["flow_code"] = output["flow_code"].astype("string")
    output["commodity_code"] = output["commodity_code"].astype("string")
    for column in ("is_reported", "is_original_classification"):
        output[column] = output[column].astype("boolean")
    output["legacy_estimation_flag"] = output["legacy_estimation_flag"].astype("string")
    output["source"] = "UN Comtrade"
    return output.sort_values(["year", "flow_code", "partner_code"]).reset_index(drop=True)


def load_partner_memberships(config_path: Path) -> pd.DataFrame:
    """Expand time-bounded YAML partner groups to a year-by-code registry."""

    payload = load_yaml(config_path)
    groups = payload.get("groups")
    if not isinstance(groups, dict):
        raise TypeError("partner_groups.yml must contain a groups mapping")
    records: list[dict[str, object]] = []
    for group_name, group_payload in groups.items():
        if not isinstance(group_payload, dict):
            continue
        members = group_payload.get("members")
        if not isinstance(members, list):
            continue
        for member in members:
            if not isinstance(member, dict):
                continue
            start = int(member["start_year"])
            end = int(member["end_year"])
            for year in range(start, end + 1):
                records.append(
                    {
                        "year": year,
                        "partner_code": int(member["code"]),
                        "partner_name": str(member["name"]),
                        "partner_group": str(group_name),
                    }
                )
    return pd.DataFrame.from_records(records)


def classify_partner_groups(trade: pd.DataFrame, memberships: pd.DataFrame) -> pd.DataFrame:
    """Attach historical partner groups and assign unmatched records to `rest_of_world`."""

    merged = trade.merge(memberships, on=["year", "partner_code"], how="left", validate="m:1")
    merged["partner_group"] = merged["partner_group"].fillna("rest_of_world")
    merged["partner_name"] = merged["partner_name"].fillna("")
    return merged


def aggregate_trade_orientation(classified: pd.DataFrame) -> pd.DataFrame:
    """Compute annual trade values and shares by historical partner group."""

    if classified.empty:
        return pd.DataFrame(
            columns=["year", "flow_code", "partner_group", "trade_value_usd", "flow_share"]
        )
    grouped = classified.groupby(
        ["year", "flow_code", "partner_group"],
        as_index=False,
    ).sum(numeric_only=True, min_count=1)
    grouped = grouped.sort_values(["year", "flow_code", "partner_group"])
    totals = (
        grouped.groupby(["year", "flow_code"])["trade_value_usd"].transform("sum").replace(0, pd.NA)
    )
    grouped["flow_share"] = grouped["trade_value_usd"] / totals
    return grouped.reset_index(drop=True)


def compile_comtrade_coverage_audit(
    matrix_inputs: list[pd.DataFrame],
    *,
    colonial_partner_codes: tuple[int, ...],
    expected_years: tuple[int, ...],
    expected_flow_codes: tuple[str, ...],
    preferred_classification_codes: tuple[str, ...] = ("S1", "S2"),
    territorial_definitions: pd.DataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    """Summarise raw Comtrade availability responses into audit tables and notes."""

    records = [record for frame in matrix_inputs for record in frame.to_dict(orient="records")]
    if records:
        matrix = pd.DataFrame.from_records(records)
    else:
        matrix = pd.DataFrame(
            columns=[
                "year",
                "flow_code",
                "classification_code",
                "reporter_code",
                "partner_code",
                "partner_desc",
                "commodity_code_source",
                "trade_value_usd",
                "cif_value_usd",
                "fob_value_usd",
                "is_reported",
                "is_original_classification",
                "legacy_estimation_flag",
                "is_world_record",
                "raw_records",
                "snapshot_partner_codes",
                "request_partner_codes_sha256",
                "partner_area_registry_sha256",
                "comtrade_config_sha256",
                "snapshot_status",
            ]
        )
    for column in ("is_reported", "is_original_classification", "legacy_estimation_flag"):
        if column not in matrix:
            matrix[column] = pd.NA

    key_columns = ["year", "flow_code", "classification_code", "partner_code"]
    matrix["duplicate_key"] = matrix.duplicated(key_columns, keep=False)
    rows: list[dict[str, object]] = []
    for year in expected_years:
        for flow_code in expected_flow_codes:
            subset = matrix.loc[(matrix["year"] == year) & (matrix["flow_code"] == flow_code)]
            available_classifications = sorted(
                str(value)
                for value in subset.loc[subset["trade_value_usd"].notna(), "classification_code"]
                .dropna()
                .unique()
                .tolist()
            )
            preferred_classification = _preferred_classification(
                available_classifications,
                preferred_classification_codes=preferred_classification_codes,
            )
            preferred = subset.loc[subset["classification_code"] == preferred_classification]
            world_values = preferred.loc[preferred["is_world_record"], "trade_value_usd"]
            partner_values = preferred.loc[
                ~preferred["is_world_record"], "trade_value_usd"
            ].dropna()
            world_value: float | None = (
                float(world_values.iloc[0]) if not world_values.empty else None
            )
            partner_sum: float | None = (
                float(partner_values.sum()) if not partner_values.empty else None
            )
            if world_value is None or partner_sum is None:
                selected_coverage_ratio: float | None = None
                unselected_world_value: float | None = None
                coverage_status = "not_testable"
            else:
                selected_coverage_ratio = partner_sum / world_value if world_value else None
                unselected_world_value = world_value - partner_sum
                coverage_status = "selected_partner_subset"
            present_colonies = sorted(
                int(value)
                for value in preferred.loc[
                    preferred["partner_code"].isin(colonial_partner_codes),
                    "partner_code",
                ]
                .dropna()
                .unique()
                .tolist()
            )
            rows.append(
                {
                    "year": year,
                    "flow_code": flow_code,
                    "reporter_code": 620,
                    "reporter_available": bool(available_classifications),
                    "available_classifications": ";".join(available_classifications),
                    "multiple_classifications_available": len(available_classifications) > 1,
                    "preferred_classification_for_checks": preferred_classification,
                    "colonial_partner_codes_present": ";".join(
                        str(code) for code in present_colonies
                    ),
                    "colonial_partner_count_present": len(present_colonies),
                    "world_value_usd": world_value,
                    "selected_partner_sum_usd": partner_sum,
                    "selected_coverage_ratio": selected_coverage_ratio,
                    "unselected_world_value_usd": unselected_world_value,
                    "coverage_status": coverage_status,
                    "valuation_note": _valuation_note(preferred, flow_code=flow_code),
                    **_territorial_definition_fields(
                        territorial_definitions,
                        reporter_code=620,
                        year=year,
                    ),
                }
            )

    audit = pd.DataFrame.from_records(rows)
    unresolved_years = audit.loc[~audit["reporter_available"], "year"].drop_duplicates().tolist()
    notes = "\n".join(
        [
            "UN Comtrade historical coverage audit",
            "======================================",
            "",
            "This report is generated from local raw Comtrade availability responses.",
            "Empty API responses are treated as not testable until reporting metadata and",
            "historical statistical-territory practices are reviewed.",
            "",
            "Open checks:",
            (
                "- Confirm whether missing overseas-territory partners were included in "
                "Portugal's statistical territory."
            ),
            "- Resolve value-basis rows flagged as not testable in the audit table.",
            (
                "- Resolve reporter/year gaps against UN Comtrade metadata rather than "
                "inferring absence from empty data."
            ),
            "",
            f"Years without any returned classification in this run: {unresolved_years}",
            "",
        ]
    )
    return matrix, audit, notes


def _valuation_note(frame: pd.DataFrame, *, flow_code: str) -> str:
    if frame.empty or "trade_value_usd" not in frame:
        return "Value basis not testable: selected classification has no returned rows."
    trade_values = pd.to_numeric(frame["trade_value_usd"], errors="coerce")
    if flow_code == "M":
        if "cif_value_usd" not in frame:
            return "Value basis not testable: CIF value field is absent from local snapshot."
        cif_values = pd.to_numeric(frame["cif_value_usd"], errors="coerce")
        verified = trade_values.notna() & cif_values.notna() & trade_values.eq(cif_values)
        if bool(verified.any()):
            return "Verified from local Comtrade fields: imports use CIF value as primaryValue."
        return "Value basis not testable: returned import rows do not expose matching CIF values."
    if flow_code == "X":
        if "fob_value_usd" not in frame:
            return "Value basis not testable: FOB value field is absent from local snapshot."
        fob_values = pd.to_numeric(frame["fob_value_usd"], errors="coerce")
        verified = trade_values.notna() & fob_values.notna() & trade_values.eq(fob_values)
        if bool(verified.any()):
            return "Verified from local Comtrade fields: exports use FOB value as primaryValue."
        return "Value basis not testable: returned export rows do not expose matching FOB values."
    return f"Value basis not testable for unsupported flow code {flow_code}."


def load_territorial_definition_registry(path: Path) -> pd.DataFrame:
    """Expand reviewed territorial-definition evidence to reporter-year rows."""

    if not path.exists():
        return pd.DataFrame(columns=TERRITORIAL_DEFINITION_COLUMNS)
    payload = load_yaml(path)
    records = payload.get("territorial_definitions")
    if not isinstance(records, list):
        raise TypeError("territorial_definitions.yml must contain a territorial_definitions list")
    rows: list[dict[str, object]] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        evidence = record.get("evidence", [])
        if not isinstance(evidence, list):
            evidence = []
        evidence_summary = "; ".join(
            str(item.get("source_id") or item.get("source") or "")
            for item in evidence
            if isinstance(item, dict) and (item.get("source_id") or item.get("source"))
        )
        for year in range(int(record["start_year"]), int(record["end_year"]) + 1):
            rows.append(
                {
                    "source_key": str(record["source_key"]),
                    "reporter_code": int(record["reporter_code"]),
                    "year": year,
                    "status": str(record["status"]),
                    "definition": str(record.get("definition") or ""),
                    "evidence_count": len(evidence),
                    "evidence_summary": evidence_summary,
                }
            )
    return pd.DataFrame.from_records(rows, columns=TERRITORIAL_DEFINITION_COLUMNS)


def _territorial_definition_fields(
    territorial_definitions: pd.DataFrame | None,
    *,
    reporter_code: int,
    year: int,
) -> dict[str, object]:
    default = {
        "territorial_definition_status": "requires_historical_metadata_review",
        "territorial_definition": "",
        "territorial_definition_evidence_count": 0,
        "territorial_definition_evidence_summary": "",
    }
    if territorial_definitions is None or territorial_definitions.empty:
        return default
    matches = territorial_definitions.loc[
        (territorial_definitions["reporter_code"].eq(reporter_code))
        & (territorial_definitions["year"].eq(year))
    ]
    if matches.empty:
        return default
    match = matches.iloc[0]
    status = str(match["status"])
    return {
        "territorial_definition_status": (
            "resolved" if status == "resolved" else "requires_historical_metadata_review"
        ),
        "territorial_definition": str(match["definition"]),
        "territorial_definition_evidence_count": int(match["evidence_count"]),
        "territorial_definition_evidence_summary": str(match["evidence_summary"]),
    }


def _preferred_classification(
    available_classifications: list[str],
    *,
    preferred_classification_codes: tuple[str, ...],
) -> str:
    for classification_code in preferred_classification_codes:
        if classification_code in available_classifications:
            return classification_code
    return available_classifications[0] if available_classifications else ""


def summarise_gdp_growth(frame: pd.DataFrame) -> pd.DataFrame:
    """Create deterministic summary statistics for annual GDP growth."""

    required = {"year", "value"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"GDP input is missing required columns: {sorted(missing)}")
    clean = frame.dropna(subset=["value"]).copy()
    clean["year"] = pd.to_numeric(clean["year"], errors="raise").astype("int64")
    clean["value"] = pd.to_numeric(clean["value"], errors="raise").astype("float64")
    clean = clean.sort_values("year")
    growth_values = [float(value) for value in clean["value"].tolist()]
    cumulative_index = 100.0
    for value in growth_values:
        cumulative_index *= 1.0 + value / 100.0
    return pd.DataFrame(
        [
            {
                "start_year": int(clean["year"].min()),
                "end_year": int(clean["year"].max()),
                "observations": len(clean),
                "arithmetic_mean_growth_percent": fmean(growth_values),
                "median_growth_percent": median(growth_values),
                "minimum_growth_percent": min(growth_values),
                "maximum_growth_percent": max(growth_values),
                "cumulative_real_gdp_index_start_100": cumulative_index,
            }
        ]
    )
