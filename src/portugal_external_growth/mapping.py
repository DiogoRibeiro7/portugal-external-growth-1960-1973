"""Product-to-industry mapping utilities."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pandas as pd

from portugal_external_growth.config import load_yaml

MAPPING_COLUMNS = [
    "classification_revision",
    "commodity_code_source",
    "industry_code",
    "industry_label",
    "mapping_scope",
    "weight",
    "decision_source",
    "decision_note",
]


def load_sitc_industry_mapping(path: Path) -> pd.DataFrame:
    """Load and validate a transparent SITC-to-industry mapping."""

    payload = load_yaml(path)
    mappings = payload.get("mappings")
    if not isinstance(mappings, list):
        raise TypeError("sitc_industry_mapping.yml must contain a mappings list")
    frame = pd.DataFrame.from_records(mappings, columns=MAPPING_COLUMNS)
    if frame.empty:
        return frame
    duplicates = frame.duplicated(
        ["classification_revision", "commodity_code_source", "industry_code", "mapping_scope"],
        keep=False,
    )
    if duplicates.any():
        raise ValueError("Duplicate SITC mapping keys found")
    weight_sums = frame.groupby(
        ["classification_revision", "commodity_code_source", "mapping_scope"]
    )["weight"].sum()
    invalid = weight_sums.loc[(weight_sums - 1.0).abs() > 1e-8]
    if not invalid.empty:
        raise ValueError("SITC mapping weights must sum to one within each mapping scope")
    return frame.sort_values(
        ["classification_revision", "commodity_code_source", "mapping_scope", "industry_code"]
    ).reset_index(drop=True)


def build_mapping_outputs(
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Build mapping, unmapped-code, coverage, and sensitivity tables."""

    mapping = load_sitc_industry_mapping(root / "config/sitc_industry_mapping.yml")
    coverage_path = root / "data/interim/live/comtrade_coverage_matrix.csv"
    if coverage_path.exists():
        trade = pd.read_csv(coverage_path)
    else:
        trade = pd.DataFrame(
            columns=["classification_code", "commodity_code_source", "trade_value_usd"]
        )
    if "commodity_code_source" not in trade.columns:
        trade["commodity_code_source"] = "TOTAL"
    product_values = (
        trade.groupby(["classification_code", "commodity_code_source"], as_index=False)[
            "trade_value_usd"
        ].sum(min_count=1)
        if not trade.empty
        else pd.DataFrame(
            columns=["classification_code", "commodity_code_source", "trade_value_usd"]
        )
    )
    mapped_codes = set(mapping["commodity_code_source"].tolist()) if not mapping.empty else set()
    unmapped = cast(
        pd.DataFrame,
        product_values.loc[
            ~product_values["commodity_code_source"].isin(mapped_codes),
            :,
        ].copy(),
    )
    unmapped["unmapped_reason"] = "no_official_correspondence_registered"
    total_value = (
        float(product_values["trade_value_usd"].sum()) if not product_values.empty else 0.0
    )
    mapped_value = float(
        product_values.loc[
            product_values["commodity_code_source"].isin(mapped_codes), "trade_value_usd"
        ].sum()
    )
    coverage = pd.DataFrame(
        [
            {
                "classification_revision": "SITC Rev.1",
                "total_trade_value_usd": total_value,
                "mapped_trade_value_usd": mapped_value,
                "mapping_coverage_share": mapped_value / total_value if total_value else 0.0,
                "source_quality": "mapping_pending_official_correspondence",
            }
        ]
    )
    sensitivity_columns = [
        "mapping_scope",
        "classification_revision",
        "commodity_code_source",
        "industry_code",
        "weighted_trade_value_usd",
    ]
    broad = pd.DataFrame(columns=sensitivity_columns)
    narrow = pd.DataFrame(columns=sensitivity_columns)
    return mapping, unmapped, coverage, broad, narrow
