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
    "flow_code": ("flowCode",),
    "commodity_code": ("cmdCode",),
    "trade_value_usd": ("primaryValue", "TradeValue", "tradeValue"),
}


def _select_column(frame: pd.DataFrame, candidates: tuple[str, ...], target: str) -> pd.Series:
    for candidate in candidates:
        if candidate in frame.columns:
            return frame[candidate]
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
    output["trade_value_usd"] = pd.to_numeric(output["trade_value_usd"], errors="coerce")
    output["flow_code"] = output["flow_code"].astype("string")
    output["commodity_code"] = output["commodity_code"].astype("string")
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
                "trade_value_usd",
                "is_world_record",
                "raw_records",
            ]
        )

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
            preferred_classification = (
                available_classifications[0] if available_classifications else ""
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
                absolute_difference: float | None = None
                percentage_difference: float | None = None
                world_partner_status = "not_testable"
            else:
                absolute_difference = world_value - partner_sum
                percentage_difference = absolute_difference / world_value if world_value else None
                world_partner_status = (
                    "within_tolerance"
                    if percentage_difference is not None and abs(percentage_difference) <= 0.01
                    else "outside_tolerance"
                )
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
                    "classification_change_flag": len(available_classifications) > 1,
                    "preferred_classification_for_checks": preferred_classification,
                    "colonial_partner_codes_present": ";".join(
                        str(code) for code in present_colonies
                    ),
                    "colonial_partner_count_present": len(present_colonies),
                    "world_value_usd": world_value,
                    "partner_sum_usd": partner_sum,
                    "world_partner_absolute_difference": absolute_difference,
                    "world_partner_percentage_difference": percentage_difference,
                    "world_partner_status": world_partner_status,
                    "valuation_note": (
                        "Comtrade convention: imports CIF, exports FOB; verify in source metadata."
                    ),
                    "territorial_definition_status": "requires_historical_metadata_review",
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
            "- Confirm valuation metadata for each historical classification and flow.",
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
