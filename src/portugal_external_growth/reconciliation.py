"""Cross-source reconciliation tables for historical trade totals."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

RECONCILIATION_COLUMNS = [
    "year",
    "flow_code",
    "source",
    "territorial_definition",
    "source_value",
    "source_unit",
    "source_currency",
    "nominal_conversion_method",
    "coverage_definition",
    "included_partners",
    "benchmark_source",
    "benchmark_value",
    "difference_from_benchmark",
    "absolute_discrepancy",
    "percentage_discrepancy",
    "explanatory_note",
    "confidence_status",
]


def build_trade_source_comparison(root: Path) -> pd.DataFrame:
    """Build a source-preserving annual trade comparison table."""

    coverage_path = root / "results/live/comtrade_coverage_audit.csv"
    rows: list[dict[str, object]] = []
    if coverage_path.exists():
        coverage = pd.read_csv(coverage_path)
        for row in coverage.to_dict(orient="records"):
            rows.append(
                {
                    "year": int(row["year"]),
                    "flow_code": str(row["flow_code"]),
                    "source": "UN Comtrade",
                    "territorial_definition": row["territorial_definition_status"],
                    "source_value": row["world_value_usd"],
                    "source_unit": "nominal merchandise trade",
                    "source_currency": "USD",
                    "nominal_conversion_method": "source_reported_usd",
                    "coverage_definition": "Portugal reporter code 620, World partner total",
                    "included_partners": "World",
                    "benchmark_source": "UN Comtrade",
                    "benchmark_value": row["world_value_usd"],
                    "difference_from_benchmark": 0.0,
                    "absolute_discrepancy": 0.0,
                    "percentage_discrepancy": 0.0,
                    "explanatory_note": "Benchmark row; territorial definition still under review.",
                    "confidence_status": "usable_with_territorial_caveat",
                }
            )

    years = sorted({_as_int(row["year"]) for row in rows} or range(1962, 1974))
    flows = sorted({str(row["flow_code"]) for row in rows} or {"X", "M"})
    for source in ("INE", "OECD", "EFTA", "CEPII TRADHIST"):
        for year in years:
            for flow_code in flows:
                rows.append(
                    {
                        "year": year,
                        "flow_code": flow_code,
                        "source": source,
                        "territorial_definition": "not_available_locally",
                        "source_value": pd.NA,
                        "source_unit": "",
                        "source_currency": "",
                        "nominal_conversion_method": "",
                        "coverage_definition": "",
                        "included_partners": "",
                        "benchmark_source": "UN Comtrade",
                        "benchmark_value": pd.NA,
                        "difference_from_benchmark": pd.NA,
                        "absolute_discrepancy": pd.NA,
                        "percentage_discrepancy": pd.NA,
                        "explanatory_note": "No local structured source table is available yet.",
                        "confidence_status": "missing_source",
                    }
                )

    return pd.DataFrame.from_records(rows, columns=RECONCILIATION_COLUMNS).sort_values(
        ["year", "flow_code", "source"]
    )


def finalise_trade_reconciliation(comparison: pd.DataFrame) -> pd.DataFrame:
    """Compute benchmark differences without merging conflicting observations."""

    output = comparison.copy()
    benchmark = output.loc[output["source"] == output["benchmark_source"]]
    benchmark_values = {
        (int(row["year"]), str(row["flow_code"])): float(row["source_value"])
        for row in benchmark.to_dict(orient="records")
        if pd.notna(row["source_value"])
    }
    for index, row in output.iterrows():
        key = (int(row["year"]), str(row["flow_code"]))
        benchmark_value = benchmark_values.get(key)
        if benchmark_value is None or pd.isna(row["source_value"]):
            continue
        source_value = float(row["source_value"])
        difference = source_value - benchmark_value
        output.at[index, "benchmark_value"] = benchmark_value
        output.at[index, "difference_from_benchmark"] = difference
        output.at[index, "absolute_discrepancy"] = abs(difference)
        output.at[index, "percentage_discrepancy"] = (
            difference / benchmark_value if benchmark_value else pd.NA
        )
    return output


def build_trade_reconciliation_notes(comparison: pd.DataFrame) -> str:
    """Write concise notes about source coverage and unresolved gaps."""

    missing = comparison.loc[comparison["confidence_status"] == "missing_source", "source"].unique()
    return "\n".join(
        [
            "Trade source reconciliation",
            "===========================",
            "",
            "Rows are source-preserving. Conflicting totals are not averaged.",
            "UN Comtrade World partner totals are used only as the current benchmark",
            "because no local INE, OECD, EFTA, or CEPII structured total is available yet.",
            "",
            f"Missing structured sources: {', '.join(sorted(str(item) for item in missing))}",
            "",
        ]
    )


def _as_int(value: Any) -> int:
    return int(str(value))
