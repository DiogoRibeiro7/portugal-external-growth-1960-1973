"""Product-level UN Comtrade extraction planning and diagnostics."""

from __future__ import annotations

import json
from collections.abc import Hashable, Mapping
from pathlib import Path
from typing import Any, cast

import pandas as pd

from portugal_external_growth.config import load_yaml

PRODUCT_COLUMNS = [
    "year",
    "flow_code",
    "classification_code",
    "commodity_code",
    "commodity_description",
    "reporter_code",
    "reporter_desc",
    "partner_code",
    "partner_desc",
    "trade_value_usd",
    "quantity",
    "quantity_unit_code",
    "quantity_unit_abbr",
    "net_weight",
    "gross_weight",
    "is_reported",
    "is_original_classification",
    "legacy_estimation_flag",
    "is_aggregate",
    "aggregate_level",
    "source_file",
]

PLAN_COLUMNS = [
    "request_id",
    "year",
    "flow_code",
    "classification_code",
    "reporter_code",
    "partner_code",
    "commodity_code_batch",
    "commodity_code_count",
    "max_records",
    "endpoint_mode",
    "requires_subscription_key",
    "plan_status",
    "blocking_reason",
]

COVERAGE_COLUMNS = [
    "year",
    "flow_code",
    "classification_code",
    "commodity_code",
    "partner_count",
    "reported_rows",
    "original_classification_rows",
    "estimated_rows",
    "aggregate_rows",
    "trade_value_usd",
    "coverage_status",
]

WORLD_RECONCILIATION_COLUMNS = [
    "year",
    "flow_code",
    "classification_code",
    "product_sum_usd",
    "world_value_usd",
    "absolute_difference",
    "relative_difference",
    "reconciliation_status",
    "note",
]

EXTRACTION_STATUS_COLUMNS = [
    "status",
    "subscription_key_present",
    "planned_requests",
    "raw_product_snapshots",
    "normalised_rows",
    "blocking_reason",
]


def build_product_extraction_design_outputs(
    root: Path, *, subscription_key_present: bool
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """Build product-level extraction plan and local diagnostics from existing snapshots."""

    config = _product_config(root)
    plan = build_product_extraction_plan(config, subscription_key_present=subscription_key_present)
    raw_files = sorted((root / "data/raw/live/comtrade_product").glob("*.csv"))
    product = normalise_product_snapshots(raw_files, root=root)
    coverage = build_product_coverage_diagnostics(product)
    world_reconciliation = build_product_world_reconciliation(
        product,
        _read_csv(root / "data/interim/live/ine_comtrade_1962_reconciliation.csv"),
    )
    status = build_product_extraction_status(
        plan,
        product,
        raw_files=raw_files,
        subscription_key_present=subscription_key_present,
    )
    notes = build_product_extraction_notes(plan, status, coverage, world_reconciliation)
    return plan, product, coverage, world_reconciliation, status, notes


def build_product_extraction_plan(
    config: dict[str, object], *, subscription_key_present: bool
) -> pd.DataFrame:
    """Build a bounded request plan without calling the API."""

    product = config.get("product_extraction", {})
    if not isinstance(product, dict):
        product = {}
    years = [int(year) for year in product.get("years", config.get("years", []))]
    flows = [str(flow) for flow in product.get("flow_codes", config.get("flow_codes", []))]
    partners = [int(code) for code in product.get("partner_codes", [0])]
    classification = str(
        product.get("classification_code", config.get("classification_code", "S1"))
    )
    reporter = int(product.get("reporter_code", config.get("reporter_code", 620)))
    max_records = int(product.get("max_records", 250000))
    commodity_batches = product.get("commodity_code_batches", [])
    if not isinstance(commodity_batches, list):
        commodity_batches = []
    batches = [
        tuple(str(code) for code in batch)
        for batch in commodity_batches
        if isinstance(batch, list) and batch
    ]
    blocking_reasons: list[str] = []
    if not subscription_key_present:
        blocking_reasons.append("COMTRADE_SUBSCRIPTION_KEY_missing")
    if not batches:
        blocking_reasons.append("commodity_code_batches_not_registered")
    plan_status = "ready" if not blocking_reasons else "blocked"
    records: list[dict[str, object]] = []
    for year in years:
        for flow in flows:
            for partner in partners:
                request_batches = batches or [tuple()]
                for batch_index, batch in enumerate(request_batches, start=1):
                    records.append(
                        {
                            "request_id": (
                                f"PRT-{year}-{flow}-{classification}-P{partner}-B{batch_index}"
                            ),
                            "year": year,
                            "flow_code": flow,
                            "classification_code": classification,
                            "reporter_code": reporter,
                            "partner_code": partner,
                            "commodity_code_batch": ",".join(batch),
                            "commodity_code_count": len(batch),
                            "max_records": max_records,
                            "endpoint_mode": "subscription_final_data",
                            "requires_subscription_key": True,
                            "plan_status": plan_status,
                            "blocking_reason": ";".join(blocking_reasons),
                        }
                    )
    return pd.DataFrame.from_records(records, columns=PLAN_COLUMNS)


def normalise_product_snapshots(raw_files: list[Path], *, root: Path) -> pd.DataFrame:
    """Normalise locally stored product-level Comtrade CSV snapshots."""

    records: list[dict[str, object]] = []
    for path in raw_files:
        frame = pd.read_csv(path)
        for row in frame.to_dict(orient="records"):
            records.append(
                {
                    "year": _first(row, "refYear", "period"),
                    "flow_code": row.get("flowCode"),
                    "classification_code": row.get("classificationCode"),
                    "commodity_code": row.get("cmdCode"),
                    "commodity_description": row.get("cmdDesc"),
                    "reporter_code": row.get("reporterCode"),
                    "reporter_desc": row.get("reporterDesc"),
                    "partner_code": row.get("partnerCode"),
                    "partner_desc": row.get("partnerDesc"),
                    "trade_value_usd": row.get("primaryValue"),
                    "quantity": row.get("qty"),
                    "quantity_unit_code": row.get("qtyUnitCode"),
                    "quantity_unit_abbr": row.get("qtyUnitAbbr"),
                    "net_weight": row.get("netWgt"),
                    "gross_weight": row.get("grossWgt"),
                    "is_reported": row.get("isReported"),
                    "is_original_classification": row.get("isOriginalClassification"),
                    "legacy_estimation_flag": row.get("legacyEstimationFlag"),
                    "is_aggregate": row.get("isAggregate"),
                    "aggregate_level": row.get("aggrLevel"),
                    "source_file": path.relative_to(root).as_posix(),
                }
            )
    if not records:
        return pd.DataFrame(columns=PRODUCT_COLUMNS)
    output = pd.DataFrame.from_records(records, columns=PRODUCT_COLUMNS)
    for column in ("year", "reporter_code", "partner_code", "legacy_estimation_flag"):
        output[column] = pd.to_numeric(output[column], errors="coerce")
    for column in ("trade_value_usd", "quantity", "net_weight", "gross_weight"):
        output[column] = pd.to_numeric(output[column], errors="coerce")
    return output.sort_values(["year", "flow_code", "commodity_code", "partner_code"])


def build_product_coverage_diagnostics(product: pd.DataFrame) -> pd.DataFrame:
    """Build year x flow x product coverage diagnostics."""

    if product.empty:
        return pd.DataFrame(columns=COVERAGE_COLUMNS)
    grouped = product.groupby(
        ["year", "flow_code", "classification_code", "commodity_code"],
        as_index=False,
        dropna=False,
    ).agg(
        partner_count=("partner_code", "nunique"),
        reported_rows=("is_reported", _truthy_count),
        original_classification_rows=(
            "is_original_classification",
            _truthy_count,
        ),
        estimated_rows=("legacy_estimation_flag", _nonzero_count),
        aggregate_rows=("is_aggregate", _truthy_count),
        trade_value_usd=("trade_value_usd", "sum"),
    )
    grouped["coverage_status"] = "reported_product_rows"
    return grouped[COVERAGE_COLUMNS]


def build_product_world_reconciliation(
    product: pd.DataFrame, benchmark_reconciliation: pd.DataFrame
) -> pd.DataFrame:
    """Compare product sums against reconciled World values where available."""

    if product.empty:
        return pd.DataFrame(columns=WORLD_RECONCILIATION_COLUMNS)
    required_columns = {"concept", "year", "flow", "source_a_value"}
    if not required_columns.issubset(benchmark_reconciliation.columns):
        world = pd.DataFrame(columns=list(required_columns))
    else:
        world = benchmark_reconciliation.loc[
            benchmark_reconciliation["concept"].isin(["World exports", "World imports"])
        ]
    benchmark = {
        (int(row["year"]), str(row["flow"])): float(row["source_a_value"])
        for row in world.to_dict(orient="records")
        if pd.notna(row.get("source_a_value"))
    }
    records: list[dict[str, object]] = []
    product_totals = product.groupby(
        ["year", "flow_code", "classification_code"], as_index=False, dropna=False
    ).agg(product_sum_usd=("trade_value_usd", "sum"))
    for row in product_totals.to_dict(orient="records"):
        key = (int(row["year"]), str(row["flow_code"]))
        world_value = benchmark.get(key)
        product_sum = float(row["product_sum_usd"])
        if world_value is None:
            status = "benchmark_world_value_missing"
            absolute_difference: object = pd.NA
            relative_difference: object = pd.NA
        else:
            absolute_difference = product_sum - world_value
            if world_value:
                relative = absolute_difference / world_value
                relative_difference = relative
                status = (
                    "matches_world_total"
                    if abs(relative) <= 0.001
                    else "does_not_match_world_total"
                )
            else:
                relative_difference = pd.NA
                status = (
                    "matches_world_total"
                    if absolute_difference == 0
                    else "does_not_match_world_total"
                )
        records.append(
            {
                "year": key[0],
                "flow_code": key[1],
                "classification_code": row["classification_code"],
                "product_sum_usd": product_sum,
                "world_value_usd": world_value if world_value is not None else pd.NA,
                "absolute_difference": absolute_difference,
                "relative_difference": relative_difference,
                "reconciliation_status": status,
                "note": "Product rows are not converted from missing records to zero.",
            }
        )
    return pd.DataFrame.from_records(records, columns=WORLD_RECONCILIATION_COLUMNS)


def build_product_extraction_status(
    plan: pd.DataFrame,
    product: pd.DataFrame,
    *,
    raw_files: list[Path],
    subscription_key_present: bool,
) -> pd.DataFrame:
    """Summarise whether product extraction is executable locally."""

    blocking_reasons = sorted(
        {
            reason
            for text in plan.get("blocking_reason", pd.Series(dtype="object")).astype(str)
            for reason in text.split(";")
            if reason
        }
    )
    return pd.DataFrame.from_records(
        [
            {
                "status": "ready" if not blocking_reasons else "blocked",
                "subscription_key_present": subscription_key_present,
                "planned_requests": len(plan),
                "raw_product_snapshots": len(raw_files),
                "normalised_rows": len(product),
                "blocking_reason": ";".join(blocking_reasons),
            }
        ],
        columns=EXTRACTION_STATUS_COLUMNS,
    )


def build_product_extraction_notes(
    plan: pd.DataFrame,
    status: pd.DataFrame,
    coverage: pd.DataFrame,
    reconciliation: pd.DataFrame,
) -> str:
    """Write human-readable product extraction design notes."""

    status_row: dict[str, object] = (
        {str(key): value for key, value in status.iloc[0].items()} if not status.empty else {}
    )
    return "\n".join(
        [
            "Product-level UN Comtrade extraction design",
            "===========================================",
            "",
            f"Planned requests: {len(plan)}",
            f"Execution status: {status_row.get('status', 'unknown')}",
            f"Blocking reason: {status_row.get('blocking_reason', '')}",
            f"Normalised product rows: {status_row.get('normalised_rows', 0)}",
            f"Coverage diagnostic rows: {len(coverage)}",
            f"World reconciliation rows: {len(reconciliation)}",
            "",
            "Research extraction uses the subscription final-data endpoint only.",
            "Preview responses are not accepted for product-level research data.",
            "Each request is count-checked before download; over-limit requests must",
            "be split by year, flow, partner, or commodity-code batch.",
            "Missing product records are not converted to zero.",
            "",
        ]
    )


def _product_config(root: Path) -> dict[str, object]:
    payload = load_yaml(root / "config/comtrade.yml")
    config = payload.get("comtrade")
    if not isinstance(config, dict):
        raise TypeError("comtrade.yml is invalid")
    return config


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _first(row: Mapping[Hashable, Any], *keys: str) -> object:
    for key in keys:
        value = row.get(key)
        if pd.notna(value):
            return value
    return pd.NA


def product_source_files(root: Path) -> list[str]:
    """Return product raw files to include in output provenance."""

    raw_files = [
        *sorted((root / "data/raw/live/comtrade_product").glob("*.json")),
        *sorted((root / "data/raw/live/comtrade_product").glob("*.csv")),
    ]
    return [path.relative_to(root).as_posix() for path in raw_files]


def metadata_json(path: Path) -> dict[str, object]:
    """Load JSON metadata for tests and future diagnostics."""

    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _truthy_count(values: pd.Series[Any]) -> int:
    return int(values.fillna(False).astype(bool).sum())


def _nonzero_count(values: pd.Series[Any]) -> int:
    numeric = pd.to_numeric(values, errors="coerce")
    return int((numeric.fillna(0) != 0).sum())
