"""Descriptive trade-orientation result tables."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pandas as pd

from portugal_external_growth.transforms import classify_partner_groups, load_partner_memberships


def build_descriptive_trade_results(root: Path) -> dict[str, pd.DataFrame]:
    """Generate descriptive trade-orientation tables from local source-preserving data."""

    coverage_path = root / "data/interim/live/comtrade_coverage_matrix.csv"
    if not coverage_path.exists():
        empty = pd.DataFrame()
        return {
            "group_values": empty,
            "annual_shares": empty,
            "period_changes": empty,
            "product_composition": empty,
            "concentration": empty,
            "export_growth_contribution": empty,
            "missingness": empty,
        }

    coverage = pd.read_csv(coverage_path)
    partner_records = coverage.loc[
        coverage["partner_code"].notna() & coverage["partner_code"].ne(0)
    ].copy()
    partner_records["commodity_code_source"] = "TOTAL"
    partner_records["trade_value_usd"] = pd.to_numeric(
        partner_records["trade_value_usd"],
        errors="coerce",
    )
    memberships = load_partner_memberships(root / "config/partner_groups.yml")
    classified = classify_partner_groups(partner_records, memberships)
    group_values = cast(
        pd.DataFrame,
        classified.groupby(["year", "flow_code", "partner_group"], as_index=False)[
            "trade_value_usd"
        ].sum(min_count=1),
    )
    group_values = group_values.sort_values(["year", "flow_code", "partner_group"])
    totals = group_values.groupby(["year", "flow_code"])["trade_value_usd"].transform("sum")
    group_values["source_quality"] = "selected_partner_records_not_full_world"
    annual_shares = group_values.copy()
    annual_shares["annual_group_share"] = annual_shares["trade_value_usd"] / totals

    period_changes = _build_period_changes(annual_shares)
    product_composition = _build_product_composition(classified)
    concentration = _build_concentration(annual_shares)
    export_growth_contribution = _build_export_growth_contribution(group_values)
    missingness = _build_missingness(root, coverage)

    return {
        "group_values": group_values,
        "annual_shares": annual_shares,
        "period_changes": period_changes,
        "product_composition": product_composition,
        "concentration": concentration,
        "export_growth_contribution": export_growth_contribution,
        "missingness": missingness,
    }


def _build_period_changes(annual_shares: pd.DataFrame) -> pd.DataFrame:
    start = annual_shares.loc[annual_shares["year"] == 1962].rename(
        columns={
            "trade_value_usd": "value_1962_usd",
            "annual_group_share": "share_1962",
        }
    )
    end = annual_shares.loc[annual_shares["year"] == 1973].rename(
        columns={
            "trade_value_usd": "value_1973_usd",
            "annual_group_share": "share_1973",
        }
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
        relative_change = (
            absolute_change / float(value_start)
            if pd.notna(absolute_change) and float(value_start) != 0
            else pd.NA
        )
        records.append(
            {
                "flow_code": row["flow_code"],
                "partner_group": row["partner_group"],
                "value_1962_usd": value_start,
                "value_1973_usd": value_end,
                "absolute_change_usd": absolute_change,
                "relative_change": relative_change,
                "share_1962": share_start,
                "share_1973": share_end,
                "share_point_change": (
                    float(share_end) - float(share_start)
                    if pd.notna(share_start) and pd.notna(share_end)
                    else pd.NA
                ),
                "source_quality": "selected_partner_records_not_full_world",
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
    grouped["source_quality"] = "aggregate_total_only_no_product_detail"
    return grouped


def _build_concentration(annual_shares: pd.DataFrame) -> pd.DataFrame:
    hhi = annual_shares.copy()
    hhi["share_square"] = hhi["annual_group_share"] ** 2
    result = cast(
        pd.DataFrame,
        hhi.groupby(["year", "flow_code"], as_index=False)["share_square"].sum(),
    )
    return result.rename(columns={"share_square": "destination_group_hhi"})


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
    result["source_quality"] = "selected_partner_records_not_full_world"
    return result


def _build_missingness(root: Path, coverage: pd.DataFrame) -> pd.DataFrame:
    audit_path = root / "results/live/comtrade_coverage_audit.csv"
    audit = pd.read_csv(audit_path) if audit_path.exists() else pd.DataFrame()
    records = [
        {
            "dataset": "comtrade_coverage_matrix",
            "rows": len(coverage),
            "missing_trade_values": int(coverage["trade_value_usd"].isna().sum()),
            "source_quality": "preview_or_free_api_results",
        },
        {
            "dataset": "comtrade_coverage_audit",
            "rows": len(audit),
            "missing_trade_values": int(audit["world_value_usd"].isna().sum())
            if not audit.empty
            else pd.NA,
            "source_quality": "territorial_definition_under_review",
        },
    ]
    return pd.DataFrame.from_records(records)
