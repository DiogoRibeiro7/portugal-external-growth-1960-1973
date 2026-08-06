"""Normalisation and aggregation transformations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
    grouped = (
        classified.groupby(["year", "flow_code", "partner_group"], as_index=False)[
            "trade_value_usd"
        ]
        .sum(min_count=1)
        .sort_values(["year", "flow_code", "partner_group"])
    )
    totals = grouped.groupby(["year", "flow_code"])["trade_value_usd"].transform("sum")
    grouped["flow_share"] = grouped["trade_value_usd"] / totals.where(totals.ne(0))
    return grouped.reset_index(drop=True)


def summarise_gdp_growth(frame: pd.DataFrame) -> pd.DataFrame:
    """Create deterministic summary statistics for annual GDP growth."""

    required = {"year", "value"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"GDP input is missing required columns: {sorted(missing)}")
    clean = frame.dropna(subset=["value"]).copy()
    clean["value"] = pd.to_numeric(clean["value"], errors="raise")
    clean = clean.sort_values("year")
    cumulative_index = float((1.0 + clean["value"] / 100.0).prod() * 100.0)
    return pd.DataFrame(
        [
            {
                "start_year": int(clean["year"].min()),
                "end_year": int(clean["year"].max()),
                "observations": int(len(clean)),
                "arithmetic_mean_growth_percent": float(clean["value"].mean()),
                "median_growth_percent": float(clean["value"].median()),
                "minimum_growth_percent": float(clean["value"].min()),
                "maximum_growth_percent": float(clean["value"].max()),
                "cumulative_real_gdp_index_start_100": cumulative_index,
            }
        ]
    )
