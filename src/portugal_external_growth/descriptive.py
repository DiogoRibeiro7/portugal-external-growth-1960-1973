"""Descriptive trade-orientation result tables."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pandas as pd

from portugal_external_growth.transforms import load_partner_memberships


def build_descriptive_trade_results(root: Path) -> dict[str, pd.DataFrame]:
    """Generate preliminary World-denominator and diagnostic result tables."""

    coverage_path = root / "data/interim/live/comtrade_coverage_matrix.csv"
    if not coverage_path.exists():
        empty = pd.DataFrame()
        return {
            "preliminary_group_shares": empty,
            "preliminary_colonial_share": empty,
            "diagnostic_selected_group_values": empty,
            "diagnostic_selected_group_shares": empty,
            "diagnostic_period_changes": empty,
            "diagnostic_product_composition": empty,
            "diagnostic_concentration": empty,
            "diagnostic_export_growth_contribution": empty,
            "diagnostic_missingness": empty,
        }

    coverage = pd.read_csv(coverage_path)
    coverage = coverage.loc[coverage["classification_code"] == "S1"].copy()
    coverage["trade_value_usd"] = pd.to_numeric(coverage["trade_value_usd"], errors="coerce")
    memberships = load_partner_memberships(root / "config/partner_groups.yml")
    preliminary = _build_world_denominator_groups(coverage, memberships)
    diagnostics = _build_selected_partner_diagnostics(coverage, memberships)
    colonial = preliminary.loc[
        (preliminary["classification_scheme"] == "contemporaneous_institutional_membership")
        & (preliminary["partner_group"] == "colonies")
    ].copy()
    colonial = colonial.rename(
        columns={
            "trade_value_usd": "colonial_trade_value_usd",
            "world_share": "colonial_world_share",
        }
    )
    return {
        "preliminary_group_shares": preliminary,
        "preliminary_colonial_share": colonial,
        **diagnostics,
    }


def _build_world_denominator_groups(
    coverage: pd.DataFrame,
    memberships: pd.DataFrame,
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    fixed_1960 = {
        "colonies": _codes_for_group(memberships, "colonies", 1960),
        "efta_1960": _codes_for_group(memberships, "efta", 1960),
        "eec6": _codes_for_group(memberships, "eec", 1960),
    }
    geographical_europe = _codes_for_groups(memberships, {"efta", "eec"})
    for (year, flow_code), subset in coverage.groupby(["year", "flow_code"]):
        year_int = int(str(year))
        world_values = subset.loc[subset["partner_code"].eq(0), "trade_value_usd"].dropna()
        if world_values.empty:
            continue
        world_value = float(world_values.iloc[0])
        partner_values = {
            int(row["partner_code"]): float(row["trade_value_usd"])
            for row in subset.loc[
                subset["partner_code"].notna() & subset["partner_code"].ne(0)
            ].to_dict(orient="records")
            if pd.notna(row["trade_value_usd"])
        }
        schemes = {
            "contemporaneous_institutional_membership": {
                "colonies": _codes_for_group(memberships, "colonies", year_int),
                "efta_contemporaneous": _codes_for_group(memberships, "efta", year_int),
                "eec_contemporaneous": _codes_for_group(memberships, "eec", year_int),
            },
            "fixed_1960_blocs": fixed_1960,
            "geographical_europe": {
                "selected_geographical_europe": geographical_europe,
            },
        }
        for scheme, groups in schemes.items():
            assigned_total = 0.0
            for group_name, codes in groups.items():
                value = sum(partner_values.get(code, 0.0) for code in codes)
                assigned_total += value
                records.append(
                    _world_share_record(
                        year_int,
                        str(flow_code),
                        scheme,
                        group_name,
                        value,
                        world_value,
                        "selected_partner_sum",
                    )
                )
            residual = world_value - assigned_total
            records.append(
                _world_share_record(
                    year_int,
                    str(flow_code),
                    scheme,
                    "true_rest_of_world",
                    residual,
                    world_value,
                    "world_total_minus_selected_groups",
                )
            )
    return pd.DataFrame.from_records(records).sort_values(
        ["classification_scheme", "year", "flow_code", "partner_group"]
    )


def _world_share_record(
    year: int,
    flow_code: str,
    scheme: str,
    group_name: str,
    value: float,
    world_value: float,
    value_method: str,
) -> dict[str, object]:
    return {
        "year": year,
        "flow_code": flow_code,
        "classification_scheme": scheme,
        "partner_group": group_name,
        "trade_value_usd": value,
        "world_value_usd": world_value,
        "world_share": value / world_value if world_value else pd.NA,
        "value_method": value_method,
        "source_quality": "preliminary_from_comtrade_coverage_snapshot",
    }


def _build_selected_partner_diagnostics(
    coverage: pd.DataFrame,
    memberships: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    partner_records = coverage.loc[
        coverage["partner_code"].notna() & coverage["partner_code"].ne(0)
    ].copy()
    partner_records["partner_group"] = partner_records.apply(
        lambda row: _current_group(int(row["year"]), int(row["partner_code"]), memberships),
        axis=1,
    )
    partner_records["commodity_code_source"] = "TOTAL"
    group_values = cast(
        pd.DataFrame,
        partner_records.groupby(["year", "flow_code", "partner_group"], as_index=False)[
            "trade_value_usd"
        ].sum(min_count=1),
    )
    group_values = group_values.sort_values(["year", "flow_code", "partner_group"])
    totals = group_values.groupby(["year", "flow_code"])["trade_value_usd"].transform("sum")
    group_values["source_quality"] = "diagnostic_selected_partners_not_world_denominator"
    selected_shares = group_values.copy()
    selected_shares["selected_partner_share"] = selected_shares["trade_value_usd"] / totals
    return {
        "diagnostic_selected_group_values": group_values,
        "diagnostic_selected_group_shares": selected_shares,
        "diagnostic_period_changes": _build_period_changes(selected_shares),
        "diagnostic_product_composition": _build_product_composition(partner_records),
        "diagnostic_concentration": _build_concentration(selected_shares),
        "diagnostic_export_growth_contribution": _build_export_growth_contribution(group_values),
        "diagnostic_missingness": _build_missingness(coverage),
    }


def _current_group(year: int, partner_code: int, memberships: pd.DataFrame) -> str:
    matches = memberships.loc[
        (memberships["year"].eq(year)) & (memberships["partner_code"].eq(partner_code)),
        "partner_group",
    ].tolist()
    if matches:
        group = str(matches[0])
        if group == "efta":
            return "efta_contemporaneous"
        if group == "eec":
            return "eec_contemporaneous"
        return group
    return "requested_unclassified_partner"


def _codes_for_group(memberships: pd.DataFrame, group_name: str, year: int) -> set[int]:
    values = memberships.loc[
        (memberships["partner_group"].eq(group_name)) & (memberships["year"].eq(year)),
        "partner_code",
    ]
    return {int(value) for value in values.dropna().tolist()}


def _codes_for_groups(memberships: pd.DataFrame, group_names: set[str]) -> set[int]:
    values = memberships.loc[memberships["partner_group"].isin(group_names), "partner_code"]
    return {int(value) for value in values.dropna().unique().tolist()}


def _build_period_changes(selected_shares: pd.DataFrame) -> pd.DataFrame:
    start = selected_shares.loc[selected_shares["year"] == 1962].rename(
        columns={"trade_value_usd": "value_1962_usd", "selected_partner_share": "share_1962"}
    )
    end = selected_shares.loc[selected_shares["year"] == 1973].rename(
        columns={"trade_value_usd": "value_1973_usd", "selected_partner_share": "share_1973"}
    )
    endpoints = start.merge(
        end,
        on=["flow_code", "partner_group"],
        how="outer",
        suffixes=("_start", "_end"),
    )
    records: list[dict[str, object]] = []
    for row in endpoints.to_dict(orient="records"):
        value_start = row.get("value_1962_usd", pd.NA)
        value_end = row.get("value_1973_usd", pd.NA)
        share_start = row.get("share_1962", pd.NA)
        share_end = row.get("share_1973", pd.NA)
        absolute_change = (
            float(value_end) - float(value_start)
            if pd.notna(value_start) and pd.notna(value_end)
            else pd.NA
        )
        records.append(
            {
                "flow_code": row["flow_code"],
                "partner_group": row["partner_group"],
                "value_1962_usd": value_start,
                "value_1973_usd": value_end,
                "absolute_change_usd": absolute_change,
                "relative_change": (
                    absolute_change / float(value_start)
                    if pd.notna(absolute_change) and float(value_start) != 0
                    else pd.NA
                ),
                "share_1962": share_start,
                "share_1973": share_end,
                "share_point_change": (
                    float(share_end) - float(share_start)
                    if pd.notna(share_start) and pd.notna(share_end)
                    else pd.NA
                ),
                "source_quality": "diagnostic_selected_partners_not_world_denominator",
            }
        )
    return pd.DataFrame.from_records(records)


def _build_product_composition(classified: pd.DataFrame) -> pd.DataFrame:
    grouped = cast(
        pd.DataFrame,
        classified.groupby(
            ["year", "flow_code", "partner_group", "commodity_code_source"],
            as_index=False,
        )["trade_value_usd"].sum(min_count=1),
    )
    totals = grouped.groupby(["year", "flow_code", "partner_group"])["trade_value_usd"].transform(
        "sum"
    )
    grouped["product_share_within_group"] = grouped["trade_value_usd"] / totals
    grouped["source_quality"] = "diagnostic_aggregate_total_only_no_product_detail"
    return grouped


def _build_concentration(selected_shares: pd.DataFrame) -> pd.DataFrame:
    hhi = selected_shares.copy()
    hhi["share_square"] = hhi["selected_partner_share"] ** 2
    result = cast(
        pd.DataFrame,
        hhi.groupby(["year", "flow_code"], as_index=False)["share_square"].sum(),
    )
    return result.rename(columns={"share_square": "selected_group_hhi"})


def _build_export_growth_contribution(group_values: pd.DataFrame) -> pd.DataFrame:
    exports = group_values.loc[group_values["flow_code"] == "X"]
    endpoints = exports.loc[exports["year"].isin([1962, 1973])]
    pivot = endpoints.pivot_table(
        index="partner_group",
        columns="year",
        values="trade_value_usd",
        aggfunc="first",
    )
    if 1962 not in pivot or 1973 not in pivot:
        return pd.DataFrame(
            columns=["partner_group", "export_growth_usd", "contribution_to_export_growth"]
        )
    growth = pivot[1973] - pivot[1962]
    total_growth = float(growth.sum())
    result = growth.reset_index(name="export_growth_usd")
    result["contribution_to_export_growth"] = (
        result["export_growth_usd"] / total_growth if total_growth else pd.NA
    )
    result["source_quality"] = "diagnostic_selected_partners_not_world_denominator"
    return result


def _build_missingness(coverage: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "dataset": "comtrade_coverage_matrix",
                "rows": len(coverage),
                "missing_trade_values": int(coverage["trade_value_usd"].isna().sum()),
                "source_quality": "preview_or_free_api_results",
            }
        ]
    )
