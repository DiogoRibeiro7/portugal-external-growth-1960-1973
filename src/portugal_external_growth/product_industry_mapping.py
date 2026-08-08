"""Product-to-industry mapping and blocked-output diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pandas as pd

from portugal_external_growth.config import load_yaml
from portugal_external_growth.partners import load_historical_group_memberships
from portugal_external_growth.product_trade import PRODUCT_COLUMNS
from portugal_external_growth.transforms import load_partner_memberships

PRODUCT_INDUSTRY_MAPPING_COLUMNS = [
    "mapping_version",
    "source_classification",
    "commodity_code",
    "commodity_description",
    "target_industry_code",
    "target_industry_group",
    "target_industry_label",
    "mapping_scope",
    "mapping_method",
    "mapping_confidence",
    "mapping_weight",
    "evidence_source",
    "evidence_reference",
    "one_to_many",
    "many_to_one",
    "notes",
]

UNMAPPED_PRODUCT_COLUMNS = [
    "year",
    "flow_code",
    "source_classification",
    "commodity_code",
    "commodity_description",
    "trade_value_usd",
    "unmapped_reason",
]

MAPPING_COVERAGE_COLUMNS = [
    "source_classification",
    "mapping_scope",
    "total_product_trade_value_usd",
    "mapped_product_trade_value_usd",
    "unmapped_product_trade_value_usd",
    "mapping_coverage_share",
    "product_count",
    "mapped_product_count",
    "unmapped_product_count",
    "coverage_status",
    "blocking_reason",
]

INDUSTRY_PANEL_COLUMNS = [
    "year",
    "flow_code",
    "source_classification",
    "mapping_scope",
    "mapping_version",
    "target_industry_code",
    "target_industry_group",
    "target_industry_label",
    "partner_group",
    "trade_value_usd",
    "product_count",
    "mapping_weight",
    "coverage_count",
    "expected_count",
    "coverage_ratio",
    "estimate_status",
    "source_quality",
]

INDUSTRY_RECONCILIATION_COLUMNS = [
    "year",
    "flow_code",
    "source_classification",
    "mapping_scope",
    "product_trade_value_usd",
    "mapped_trade_value_usd",
    "unmapped_trade_value_usd",
    "absolute_difference",
    "reconciliation_status",
    "note",
]

PRODUCT_MAPPING_STATUS_COLUMNS = [
    "status",
    "product_rows",
    "mapping_rows",
    "coverage_rows",
    "industry_panel_rows",
    "max_mapping_coverage_share",
    "blocking_reason",
]


def load_product_industry_mapping(path: Path) -> pd.DataFrame:
    """Load and validate a source-grounded product-to-industry mapping table."""

    payload = load_yaml(path)
    mapping_version = str(payload.get("mapping_version", "unversioned"))
    mappings = payload.get("mappings")
    if not isinstance(mappings, list):
        raise TypeError("product_industry_mapping.yml must contain a mappings list")
    records = [
        {
            "mapping_version": str(record.get("mapping_version", mapping_version)),
            **record,
        }
        for record in mappings
        if isinstance(record, dict)
    ]
    frame = pd.DataFrame.from_records(records, columns=PRODUCT_INDUSTRY_MAPPING_COLUMNS)
    if frame.empty:
        return frame
    for column in (
        "mapping_version",
        "source_classification",
        "commodity_code",
        "target_industry_code",
        "mapping_scope",
    ):
        frame[column] = frame[column].astype(str)
    duplicates = frame.duplicated(
        [
            "mapping_version",
            "source_classification",
            "commodity_code",
            "target_industry_code",
            "mapping_scope",
        ],
        keep=False,
    )
    if duplicates.any():
        raise ValueError("Duplicate product-to-industry mapping keys found")
    frame["mapping_weight"] = pd.to_numeric(frame["mapping_weight"], errors="coerce")
    if frame["mapping_weight"].isna().any():
        raise ValueError("Product-to-industry mapping weights must be numeric")
    weight_sums = frame.groupby(
        ["mapping_version", "source_classification", "commodity_code", "mapping_scope"]
    )["mapping_weight"].sum()
    invalid = weight_sums.loc[(weight_sums - 1.0).abs() > 1e-8]
    if not invalid.empty:
        raise ValueError(
            "Product-to-industry mapping weights must sum to one within each mapping scope"
        )
    frame["one_to_many"] = frame.duplicated(
        ["mapping_version", "source_classification", "commodity_code", "mapping_scope"],
        keep=False,
    )
    frame["many_to_one"] = frame.duplicated(
        ["mapping_version", "source_classification", "target_industry_code", "mapping_scope"],
        keep=False,
    )
    return frame.sort_values(
        [
            "mapping_version",
            "source_classification",
            "commodity_code",
            "mapping_scope",
            "target_industry_code",
        ]
    ).reset_index(drop=True)


def build_product_industry_mapping_outputs(
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """Build mapping, coverage, panel, reconciliation, status, and notes."""

    product = _read_product(root / "data/interim/live/comtrade_product_normalised.csv")
    mapping_path = root / "config/product_industry_mapping.yml"
    mapping = (
        load_product_industry_mapping(mapping_path)
        if mapping_path.exists()
        else pd.DataFrame(columns=PRODUCT_INDUSTRY_MAPPING_COLUMNS)
    )
    product_values = _product_values(product)
    unmapped = build_unmapped_products(product_values, mapping)
    coverage = build_mapping_coverage(product_values, mapping)
    panel = build_industry_trade_panel(product, mapping, root)
    reconciliation = build_industry_reconciliation(product_values, mapping)
    status = build_product_mapping_status(product, mapping, coverage, panel, root)
    notes = build_product_mapping_notes(status, coverage, reconciliation)
    return mapping, unmapped, coverage, panel, reconciliation, status, notes


def build_unmapped_products(product_values: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    """List product rows that cannot yet be mapped to an industry."""

    if product_values.empty:
        return pd.DataFrame(columns=UNMAPPED_PRODUCT_COLUMNS)
    mapped_keys = _mapped_keys(mapping)
    output = product_values.loc[
        ~product_values.apply(
            lambda row: (str(row["source_classification"]), str(row["commodity_code"]))
            in mapped_keys,
            axis=1,
        )
    ].copy()
    output["unmapped_reason"] = (
        "no_product_industry_mapping_registered"
        if mapping.empty
        else "commodity_code_not_in_product_industry_mapping"
    )
    return output[UNMAPPED_PRODUCT_COLUMNS].sort_values(
        ["year", "flow_code", "source_classification", "commodity_code"]
    )


def build_mapping_coverage(product_values: pd.DataFrame, mapping: pd.DataFrame) -> pd.DataFrame:
    """Calculate product-to-industry mapping coverage by source classification and scope."""

    if product_values.empty:
        return pd.DataFrame(columns=MAPPING_COVERAGE_COLUMNS)
    scopes = (
        sorted(mapping["mapping_scope"].astype(str).unique().tolist())
        if not mapping.empty
        else [""]
    )
    records: list[dict[str, object]] = []
    for source_classification, subset in product_values.groupby("source_classification"):
        total_value = float(subset["trade_value_usd"].sum())
        total_products = int(subset["commodity_code"].nunique())
        for scope in scopes:
            scoped = mapping.loc[mapping["mapping_scope"].astype(str).eq(scope)]
            mapped_codes = set(
                scoped.loc[
                    scoped["source_classification"].astype(str).eq(str(source_classification)),
                    "commodity_code",
                ].astype(str)
            )
            mapped_subset = subset.loc[subset["commodity_code"].astype(str).isin(mapped_codes)]
            mapped_value = float(mapped_subset["trade_value_usd"].sum())
            mapped_products = int(mapped_subset["commodity_code"].nunique())
            share = mapped_value / total_value if total_value else 0.0
            blocking_reason = "" if mapped_products else "no_product_industry_mapping_registered"
            records.append(
                {
                    "source_classification": source_classification,
                    "mapping_scope": scope,
                    "total_product_trade_value_usd": total_value,
                    "mapped_product_trade_value_usd": mapped_value,
                    "unmapped_product_trade_value_usd": total_value - mapped_value,
                    "mapping_coverage_share": share,
                    "product_count": total_products,
                    "mapped_product_count": mapped_products,
                    "unmapped_product_count": total_products - mapped_products,
                    "coverage_status": "complete" if share == 1.0 else "incomplete",
                    "blocking_reason": blocking_reason,
                }
            )
    return pd.DataFrame.from_records(records, columns=MAPPING_COVERAGE_COLUMNS)


def build_industry_trade_panel(
    product: pd.DataFrame, mapping: pd.DataFrame, root: Path
) -> pd.DataFrame:
    """Aggregate mapped product rows to industry x partner-group x year."""

    if product.empty or mapping.empty:
        return pd.DataFrame(columns=INDUSTRY_PANEL_COLUMNS)
    product = product.copy()
    product["source_classification"] = product["classification_code"].astype(str)
    product["commodity_code"] = product["commodity_code"].astype(str)
    merged = product.merge(
        mapping,
        on=["source_classification", "commodity_code"],
        how="inner",
        suffixes=("", "_mapping"),
    )
    if merged.empty:
        return pd.DataFrame(columns=INDUSTRY_PANEL_COLUMNS)
    merged["trade_value_usd"] = pd.to_numeric(merged["trade_value_usd"], errors="coerce")
    merged["weighted_trade_value_usd"] = merged["trade_value_usd"] * merged["mapping_weight"]
    assigned = _assign_partner_groups(merged, _load_memberships(root))
    grouped = assigned.groupby(
        [
            "year",
            "flow_code",
            "source_classification",
            "mapping_scope",
            "mapping_version",
            "target_industry_code",
            "target_industry_group",
            "target_industry_label",
            "partner_group",
        ],
        as_index=False,
        dropna=False,
    ).agg(
        trade_value_usd=("weighted_trade_value_usd", "sum"),
        product_count=("commodity_code", "nunique"),
        mapping_weight=("mapping_weight", "sum"),
    )
    grouped["coverage_count"] = grouped["product_count"]
    grouped["expected_count"] = grouped["product_count"]
    grouped["coverage_ratio"] = 1.0
    grouped["estimate_status"] = "mapped_observed_product_rows"
    grouped["source_quality"] = "product_level_trade_with_registered_industry_mapping"
    return grouped[INDUSTRY_PANEL_COLUMNS].sort_values(
        ["year", "flow_code", "mapping_scope", "target_industry_code", "partner_group"]
    )


def build_industry_reconciliation(
    product_values: pd.DataFrame, mapping: pd.DataFrame
) -> pd.DataFrame:
    """Reconcile mapped plus unmapped product values to product-level totals."""

    if product_values.empty:
        return pd.DataFrame(columns=INDUSTRY_RECONCILIATION_COLUMNS)
    scopes = (
        sorted(mapping["mapping_scope"].astype(str).unique().tolist())
        if not mapping.empty
        else [""]
    )
    records: list[dict[str, object]] = []
    for (year, flow, source_classification), subset in product_values.groupby(
        ["year", "flow_code", "source_classification"],
        dropna=False,
    ):
        product_total = float(subset["trade_value_usd"].sum())
        for scope in scopes:
            scoped = mapping.loc[mapping["mapping_scope"].astype(str).eq(scope)]
            mapped_codes = set(
                scoped.loc[
                    scoped["source_classification"].astype(str).eq(str(source_classification)),
                    "commodity_code",
                ].astype(str)
            )
            mapped_value = float(
                subset.loc[subset["commodity_code"].astype(str).isin(mapped_codes)][
                    "trade_value_usd"
                ].sum()
            )
            unmapped_value = product_total - mapped_value
            difference = product_total - mapped_value - unmapped_value
            records.append(
                {
                    "year": year,
                    "flow_code": flow,
                    "source_classification": source_classification,
                    "mapping_scope": scope,
                    "product_trade_value_usd": product_total,
                    "mapped_trade_value_usd": mapped_value,
                    "unmapped_trade_value_usd": unmapped_value,
                    "absolute_difference": difference,
                    "reconciliation_status": (
                        "reconciles_to_product_total"
                        if abs(difference) <= 1e-8
                        else "does_not_reconcile_to_product_total"
                    ),
                    "note": "Missing product records are not converted to zero.",
                }
            )
    return pd.DataFrame.from_records(records, columns=INDUSTRY_RECONCILIATION_COLUMNS)


def build_product_mapping_status(
    product: pd.DataFrame,
    mapping: pd.DataFrame,
    coverage: pd.DataFrame,
    panel: pd.DataFrame,
    root: Path,
) -> pd.DataFrame:
    """Summarise whether product-to-industry outputs are analytically usable."""

    reasons: list[str] = []
    product_status = _product_extraction_status(root)
    if product.empty:
        reasons.append("product_level_trade_not_validated")
    if product_status and product_status != "ready":
        reasons.append(f"product_extraction_status_{product_status}")
    if mapping.empty:
        reasons.append("product_industry_mapping_not_registered")
    max_coverage = (
        float(pd.to_numeric(coverage["mapping_coverage_share"], errors="coerce").fillna(0).max())
        if not coverage.empty
        else 0.0
    )
    if max_coverage <= 0.0:
        reasons.append("product_industry_mapping_coverage_zero")
    unique_reasons = sorted(set(reasons))
    return pd.DataFrame.from_records(
        [
            {
                "status": "ready" if not unique_reasons else "blocked",
                "product_rows": len(product),
                "mapping_rows": len(mapping),
                "coverage_rows": len(coverage),
                "industry_panel_rows": len(panel),
                "max_mapping_coverage_share": max_coverage,
                "blocking_reason": ";".join(unique_reasons),
            }
        ],
        columns=PRODUCT_MAPPING_STATUS_COLUMNS,
    )


def build_product_mapping_notes(
    status: pd.DataFrame, coverage: pd.DataFrame, reconciliation: pd.DataFrame
) -> str:
    """Build a human-readable product-to-industry mapping report."""

    row = {str(key): value for key, value in status.iloc[0].items()} if not status.empty else {}
    return "\n".join(
        [
            "Product-to-industry mapping readiness",
            "=====================================",
            "",
            f"Status: {row.get('status', 'unknown')}",
            f"Blocking reason: {row.get('blocking_reason', '')}",
            f"Product rows: {row.get('product_rows', 0)}",
            f"Mapping rows: {row.get('mapping_rows', 0)}",
            f"Coverage rows: {len(coverage)}",
            f"Industry panel rows: {row.get('industry_panel_rows', 0)}",
            f"Reconciliation rows: {len(reconciliation)}",
            "",
            "The industry panel remains empty until product-level Comtrade rows are",
            "validated and source-grounded commodity-to-industry mappings are registered.",
            "Unobserved product records are not interpreted as zero trade.",
            "",
        ]
    )


def _product_values(product: pd.DataFrame) -> pd.DataFrame:
    if product.empty:
        return pd.DataFrame(columns=UNMAPPED_PRODUCT_COLUMNS[:-1])
    frame = product.copy()
    frame["source_classification"] = frame["classification_code"].astype(str)
    frame["commodity_code"] = frame["commodity_code"].astype(str)
    frame["trade_value_usd"] = pd.to_numeric(frame["trade_value_usd"], errors="coerce")
    grouped = cast(
        pd.DataFrame,
        frame.groupby(
            [
                "year",
                "flow_code",
                "source_classification",
                "commodity_code",
                "commodity_description",
            ],
            as_index=False,
            dropna=False,
        )["trade_value_usd"].sum(min_count=1),
    )
    return grouped[UNMAPPED_PRODUCT_COLUMNS[:-1]]


def _mapped_keys(mapping: pd.DataFrame) -> set[tuple[str, str]]:
    if mapping.empty:
        return set()
    return {
        (str(row["source_classification"]), str(row["commodity_code"]))
        for row in mapping.to_dict(orient="records")
    }


def _assign_partner_groups(product: pd.DataFrame, memberships: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for row in product.to_dict(orient="records"):
        year = int(row["year"])
        partner_code = int(row["partner_code"])
        if partner_code == 0:
            groups = ["world_total"]
        else:
            groups = (
                memberships.loc[
                    memberships["year"].eq(year) & memberships["partner_code"].eq(partner_code),
                    "partner_group",
                ]
                .astype(str)
                .tolist()
            )
            if not groups:
                groups = ["unclassified_partner"]
        for group in groups:
            record = {str(key): value for key, value in row.items()}
            record["partner_group"] = group
            records.append(record)
    return pd.DataFrame.from_records(records)


def _load_memberships(root: Path) -> pd.DataFrame:
    historical = root / "config/historical_groups.yml"
    areas = root / "config/comtrade_partner_areas.yml"
    if historical.exists() and areas.exists():
        return load_historical_group_memberships(historical, areas)
    return load_partner_memberships(root / "config/partner_groups.yml")


def _product_extraction_status(root: Path) -> str:
    status_path = root / "results/live/comtrade_product_extraction_status.csv"
    if not status_path.exists():
        return ""
    status = pd.read_csv(status_path)
    if status.empty or "status" not in status.columns:
        return ""
    return str(status.loc[0, "status"])


def _read_product(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=PRODUCT_COLUMNS)
    return pd.read_csv(path, dtype={"classification_code": "string", "commodity_code": "string"})
