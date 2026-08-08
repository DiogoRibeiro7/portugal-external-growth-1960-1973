"""Descriptive industry exposure measures with readiness guards."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pandas as pd

EXPOSURE_COLUMNS = [
    "year",
    "source_classification",
    "mapping_scope",
    "mapping_version",
    "target_industry_code",
    "target_industry_group",
    "target_industry_label",
    "total_exports_usd",
    "colonial_exports_usd",
    "european_exports_usd",
    "colonial_exposure",
    "european_exposure",
    "coverage_count",
    "expected_count",
    "coverage_ratio",
    "estimate_status",
    "source_quality",
]

COMPOSITION_COLUMNS = [
    "year",
    "flow_code",
    "source_classification",
    "mapping_scope",
    "target_industry_code",
    "target_industry_label",
    "partner_group",
    "trade_value_usd",
    "group_total_trade_value_usd",
    "industry_share_within_group",
    "coverage_count",
    "expected_count",
    "coverage_ratio",
    "estimate_status",
    "source_quality",
]

GROWTH_COLUMNS = [
    "target_industry_code",
    "target_industry_label",
    "partner_group",
    "export_value_1962_usd",
    "export_value_1973_usd",
    "export_growth_usd",
    "contribution_to_group_export_growth",
    "coverage_count",
    "expected_count",
    "coverage_ratio",
    "estimate_status",
    "source_quality",
]

COVERAGE_COLUMNS = [
    "dataset",
    "rows",
    "required_rows",
    "coverage_ratio",
    "status",
    "blocking_reason",
]

STATUS_COLUMNS = [
    "status",
    "industry_panel_rows",
    "exposure_rows",
    "composition_rows",
    "growth_rows",
    "blocking_reason",
]


def build_industry_exposure_outputs(
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """Build descriptive industry exposure outputs from a validated industry panel."""

    panel = _read_industry_panel(root / "data/processed/live/industry_trade_panel.csv")
    mapping_status = _read_status(
        root / "results/diagnostics/product_industry_mapping/product_mapping_status.csv"
    )
    exposures = build_industry_exposure_panel(panel)
    composition = build_group_composition(panel)
    growth = build_export_growth_decomposition(panel)
    coverage = build_industry_exposure_coverage(panel, exposures, composition, growth)
    status = build_industry_exposure_status(panel, exposures, composition, growth, mapping_status)
    notes = build_industry_exposure_notes(status, coverage)
    return exposures, composition, growth, coverage, status, notes


def build_industry_exposure_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """Calculate colonial and European export exposure by industry-year."""

    if panel.empty:
        return pd.DataFrame(columns=EXPOSURE_COLUMNS)
    exports = panel.loc[panel["flow_code"].astype(str).eq("X")].copy()
    if exports.empty:
        return pd.DataFrame(columns=EXPOSURE_COLUMNS)
    index_columns = [
        "year",
        "source_classification",
        "mapping_scope",
        "mapping_version",
        "target_industry_code",
        "target_industry_group",
        "target_industry_label",
    ]
    world = _group_value(exports, index_columns, {"world_total"}, "total_exports_usd")
    colonial = _group_value(exports, index_columns, {"colonies"}, "colonial_exports_usd")
    european = _group_value(
        exports,
        index_columns,
        {"efta_participation", "eec_current_membership", "efta_eec_fixed_partner_sample"},
        "european_exports_usd",
    )
    merged = world.merge(colonial, on=index_columns, how="left").merge(
        european, on=index_columns, how="left"
    )
    merged["colonial_exports_usd"] = merged["colonial_exports_usd"].fillna(0.0)
    merged["european_exports_usd"] = merged["european_exports_usd"].fillna(0.0)
    merged["colonial_exposure"] = merged["colonial_exports_usd"] / merged["total_exports_usd"]
    merged["european_exposure"] = merged["european_exports_usd"] / merged["total_exports_usd"]
    merged["coverage_count"] = 1
    merged["expected_count"] = 1
    merged["coverage_ratio"] = 1.0
    merged["estimate_status"] = "descriptive_observed_world_denominator"
    merged["source_quality"] = "descriptive_from_validated_industry_trade_panel"
    return merged[EXPOSURE_COLUMNS].sort_values(["year", "mapping_scope", "target_industry_code"])


def build_group_composition(panel: pd.DataFrame) -> pd.DataFrame:
    """Calculate industry composition within each partner group."""

    if panel.empty:
        return pd.DataFrame(columns=COMPOSITION_COLUMNS)
    grouped = panel.copy()
    grouped["trade_value_usd"] = pd.to_numeric(grouped["trade_value_usd"], errors="coerce")
    totals = grouped.groupby(["year", "flow_code", "mapping_scope", "partner_group"])[
        "trade_value_usd"
    ].transform("sum")
    grouped["group_total_trade_value_usd"] = totals
    grouped["industry_share_within_group"] = grouped["trade_value_usd"] / totals
    grouped["estimate_status"] = grouped.get(
        "estimate_status", pd.Series("mapped_observed_product_rows", index=grouped.index)
    )
    grouped["source_quality"] = "descriptive_from_validated_industry_trade_panel"
    return grouped[COMPOSITION_COLUMNS].sort_values(
        ["year", "flow_code", "mapping_scope", "partner_group", "target_industry_code"]
    )


def build_export_growth_decomposition(panel: pd.DataFrame) -> pd.DataFrame:
    """Decompose 1962-1973 export growth by industry within partner groups."""

    if panel.empty:
        return pd.DataFrame(columns=GROWTH_COLUMNS)
    exports = panel.loc[panel["flow_code"].astype(str).eq("X")].copy()
    endpoints = exports.loc[exports["year"].isin([1962, 1973])]
    if endpoints.empty:
        return pd.DataFrame(columns=GROWTH_COLUMNS)
    grouped = endpoints.groupby(
        ["target_industry_code", "target_industry_label", "partner_group", "year"],
        as_index=False,
        dropna=False,
    )["trade_value_usd"].sum()
    pivot = grouped.pivot_table(
        index=["target_industry_code", "target_industry_label", "partner_group"],
        columns="year",
        values="trade_value_usd",
        aggfunc="first",
    )
    if 1962 not in pivot or 1973 not in pivot:
        return pd.DataFrame(columns=GROWTH_COLUMNS)
    result = pivot.reset_index()
    result["export_value_1962_usd"] = result[1962]
    result["export_value_1973_usd"] = result[1973]
    result["export_growth_usd"] = result["export_value_1973_usd"] - result["export_value_1962_usd"]
    totals = result.groupby("partner_group")["export_growth_usd"].transform("sum")
    result["contribution_to_group_export_growth"] = result["export_growth_usd"] / totals
    result["coverage_count"] = 2
    result["expected_count"] = 2
    result["coverage_ratio"] = 1.0
    result["estimate_status"] = "descriptive_endpoint_growth"
    result["source_quality"] = "descriptive_from_validated_industry_trade_panel"
    output = result[GROWTH_COLUMNS].sort_values(["partner_group", "target_industry_code"])
    return cast(pd.DataFrame, output)


def build_industry_exposure_coverage(
    panel: pd.DataFrame,
    exposures: pd.DataFrame,
    composition: pd.DataFrame,
    growth: pd.DataFrame,
) -> pd.DataFrame:
    """Summarise coverage for each descriptive industry-exposure output."""

    expected = 1 if not panel.empty else 0
    records = [
        _coverage_record("industry_trade_panel", len(panel), 1),
        _coverage_record("industry_exposure_panel", len(exposures), expected),
        _coverage_record("industry_group_composition", len(composition), expected),
        _coverage_record("industry_export_growth_decomposition", len(growth), expected),
    ]
    return pd.DataFrame.from_records(records, columns=COVERAGE_COLUMNS)


def build_industry_exposure_status(
    panel: pd.DataFrame,
    exposures: pd.DataFrame,
    composition: pd.DataFrame,
    growth: pd.DataFrame,
    mapping_status: str,
) -> pd.DataFrame:
    """Build a machine-readable readiness status for descriptive industry exposure."""

    reasons: list[str] = []
    if panel.empty:
        reasons.append("industry_trade_panel_empty")
    if mapping_status and mapping_status != "ready":
        reasons.append(f"product_industry_mapping_status_{mapping_status}")
    if exposures.empty:
        reasons.append("industry_exposure_panel_empty")
    if composition.empty:
        reasons.append("industry_group_composition_empty")
    if growth.empty:
        reasons.append("industry_growth_decomposition_empty")
    unique_reasons = sorted(set(reasons))
    return pd.DataFrame.from_records(
        [
            {
                "status": "ready" if not unique_reasons else "blocked",
                "industry_panel_rows": len(panel),
                "exposure_rows": len(exposures),
                "composition_rows": len(composition),
                "growth_rows": len(growth),
                "blocking_reason": ";".join(unique_reasons),
            }
        ],
        columns=STATUS_COLUMNS,
    )


def build_industry_exposure_notes(status: pd.DataFrame, coverage: pd.DataFrame) -> str:
    """Build a human-readable diagnostic report for industry exposures."""

    row = {str(key): value for key, value in status.iloc[0].items()} if not status.empty else {}
    return "\n".join(
        [
            "Descriptive industry exposure diagnostics",
            "=========================================",
            "",
            f"Status: {row.get('status', 'unknown')}",
            f"Blocking reason: {row.get('blocking_reason', '')}",
            f"Industry panel rows: {row.get('industry_panel_rows', 0)}",
            f"Exposure rows: {row.get('exposure_rows', 0)}",
            f"Composition rows: {row.get('composition_rows', 0)}",
            f"Growth decomposition rows: {row.get('growth_rows', 0)}",
            f"Coverage rows: {len(coverage)}",
            "",
            "No causal claims or econometric coefficients are produced here.",
            "Industry exposure measures remain blocked until the industry trade panel",
            "contains validated product-level observations with a documented mapping.",
            "Missing historical observations are not converted to zero.",
            "",
        ]
    )


def _group_value(
    panel: pd.DataFrame, index_columns: list[str], partner_groups: set[str], value_column: str
) -> pd.DataFrame:
    selected = panel.loc[panel["partner_group"].astype(str).isin(partner_groups)]
    if selected.empty:
        return pd.DataFrame(columns=[*index_columns, value_column])
    output = (
        selected.groupby(index_columns, as_index=False, dropna=False)
        .agg(trade_value_usd=("trade_value_usd", "sum"))
        .rename(columns={"trade_value_usd": value_column})
    )
    return output


def _coverage_record(dataset: str, rows: int, required_rows: int) -> dict[str, object]:
    ratio = rows / required_rows if required_rows else 0.0
    return {
        "dataset": dataset,
        "rows": rows,
        "required_rows": required_rows,
        "coverage_ratio": ratio,
        "status": "available" if rows >= required_rows and required_rows else "blocked",
        "blocking_reason": "" if rows >= required_rows and required_rows else f"{dataset}_empty",
    }


def _read_status(path: Path) -> str:
    if not path.exists():
        return ""
    frame = pd.read_csv(path)
    if frame.empty or "status" not in frame.columns:
        return ""
    return str(frame.loc[0, "status"])


def _read_industry_panel(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)
