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
    trade["classification_revision"] = trade["classification_code"].map(_classification_revision)
    product_values = (
        trade.groupby(
            ["classification_code", "classification_revision", "commodity_code_source"],
            as_index=False,
        )["trade_value_usd"].sum(min_count=1)
        if not trade.empty
        else pd.DataFrame(
            columns=[
                "classification_code",
                "classification_revision",
                "commodity_code_source",
                "trade_value_usd",
            ]
        )
    )
    mapped_keys = (
        set(zip(mapping["classification_revision"], mapping["commodity_code_source"], strict=True))
        if not mapping.empty
        else set()
    )
    product_values["is_mapped"] = product_values.apply(
        lambda row: (row["classification_revision"], row["commodity_code_source"]) in mapped_keys,
        axis=1,
    )
    unmapped = cast(
        pd.DataFrame,
        product_values.loc[
            ~product_values["is_mapped"],
            :,
        ].copy(),
    )
    unmapped = unmapped.drop(columns=["is_mapped"])
    unmapped["unmapped_reason"] = "no_official_correspondence_registered"
    if product_values.empty:
        coverage = pd.DataFrame(
            columns=[
                "classification_code",
                "classification_revision",
                "total_trade_value_usd",
                "mapped_trade_value_usd",
                "mapping_coverage_share",
                "source_quality",
            ]
        )
    else:
        totals = cast(
            pd.DataFrame,
            product_values.groupby(
                ["classification_code", "classification_revision"], as_index=False
            )["trade_value_usd"].sum(min_count=1),
        ).rename(columns={"trade_value_usd": "total_trade_value_usd"})
        mapped = cast(
            pd.DataFrame,
            product_values.loc[product_values["is_mapped"]]
            .groupby(["classification_code", "classification_revision"], as_index=False)[
                "trade_value_usd"
            ]
            .sum(min_count=1),
        ).rename(columns={"trade_value_usd": "mapped_trade_value_usd"})
        coverage = totals.merge(
            mapped,
            on=["classification_code", "classification_revision"],
            how="left",
        )
        coverage["total_trade_value_usd"] = coverage["total_trade_value_usd"].fillna(0.0)
        coverage["mapped_trade_value_usd"] = coverage["mapped_trade_value_usd"].fillna(0.0)
        coverage["mapping_coverage_share"] = (
            coverage["mapped_trade_value_usd"] / coverage["total_trade_value_usd"]
        ).fillna(0.0)
        coverage["source_quality"] = "mapping_pending_official_correspondence"
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


def _classification_revision(classification_code: object) -> str:
    labels = {
        "S1": "SITC Rev.1",
        "S2": "SITC Rev.2",
        "S3": "SITC Rev.3",
        "S4": "SITC Rev.4",
    }
    return labels.get(str(classification_code), f"Comtrade {classification_code}")
