"""Cross-source reconciliation tables for historical trade totals."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pandas as pd

from portugal_external_growth.partners import load_historical_group_memberships

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

INE_COMTRADE_1962_COLUMNS = [
    "year",
    "flow",
    "concept",
    "source_a",
    "source_b",
    "source_a_value",
    "source_b_value",
    "absolute_difference",
    "relative_difference",
    "unit",
    "valuation_basis",
    "territorial_definition_a",
    "territorial_definition_b",
    "reconciliation_status",
    "explanation",
    "evidence_reference",
    "signed_difference",
    "relative_difference_denominator",
    "source_a_original_value",
    "source_a_currency",
    "source_b_original_value",
    "source_b_currency",
    "conversion_method",
    "expected_partner_count",
    "observed_partner_count",
    "coverage_ratio",
    "missing_partner_entities",
]

RECONCILIATION_REGISTRY_COLUMNS = [
    "reconciliation_id",
    "benchmark_year",
    "source_a",
    "source_b",
    "row_count",
    "reconciled_row_count",
    "unresolved_row_count",
    "overall_status",
    "blocking_reasons",
    "evidence_reference",
]

PTE_PER_USD_DIAGNOSTIC_1962 = 28.75


def build_trade_source_comparison(root: Path) -> pd.DataFrame:
    """Build a source-preserving annual trade comparison table."""

    coverage_path = root / "results/diagnostics/comtrade_coverage/comtrade_coverage_audit.csv"
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

    ine_keys: set[tuple[int, str]] = set()
    ine_aggregates = _load_ine_1962_aggregates(root)
    if not ine_aggregates.empty:
        for ine_record in cast(
            list[dict[str, object]],
            ine_aggregates.loc[ine_aggregates["partner_group_source"].eq("World")].to_dict(
                orient="records"
            ),
        ):
            year = _as_int(ine_record["reference_year"])
            flow_code = str(ine_record["flow"])
            source_value = _ine_pte_value(ine_record) / PTE_PER_USD_DIAGNOSTIC_1962
            ine_keys.add((year, flow_code))
            rows.append(
                {
                    "year": year,
                    "flow_code": flow_code,
                    "source": "INE",
                    "territorial_definition": ine_record["territorial_definition"],
                    "source_value": source_value,
                    "source_unit": "nominal merchandise trade",
                    "source_currency": "USD",
                    "nominal_conversion_method": (
                        "diagnostic_conversion_at_28.75_PTE_per_USD;"
                        " exchange_rate_source_not_registered"
                    ),
                    "coverage_definition": "INE special-trade World total",
                    "included_partners": "World",
                    "benchmark_source": "UN Comtrade",
                    "benchmark_value": pd.NA,
                    "difference_from_benchmark": pd.NA,
                    "absolute_discrepancy": pd.NA,
                    "percentage_discrepancy": pd.NA,
                    "explanatory_note": (
                        "Validated double-entry INE aggregate; converted only for diagnostic "
                        "comparison pending exchange-rate and territorial-definition evidence."
                    ),
                    "confidence_status": "usable_with_conversion_and_territorial_caveat",
                }
            )

    years = sorted({_as_int(row["year"]) for row in rows} or range(1962, 1974))
    flows = sorted({str(row["flow_code"]) for row in rows} or {"X", "M"})
    for source in ("INE", "OECD", "EFTA", "CEPII TRADHIST"):
        for year in years:
            for flow_code in flows:
                if source == "INE" and (year, flow_code) in ine_keys:
                    continue
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


def build_ine_comtrade_1962_reconciliation(root: Path) -> pd.DataFrame:
    """Compare verified 1962 INE aggregates with the local Comtrade snapshot."""

    ine = _load_ine_1962_aggregates(root)
    audit = _read_optional_csv(
        root / "results/diagnostics/comtrade_coverage/comtrade_coverage_audit.csv"
    )
    matrix = _read_optional_csv(root / "data/interim/live/comtrade_coverage_matrix.csv")
    if ine.empty or audit.empty:
        return pd.DataFrame(columns=INE_COMTRADE_1962_COLUMNS)

    rows: list[dict[str, object]] = []
    for flow, concept in (("X", "World exports"), ("M", "World imports")):
        ine_row = _ine_aggregate_row(ine, flow=flow, partner_group="World")
        audit_row = _comtrade_world_row(audit, flow=flow)
        if ine_row is None or audit_row is None:
            continue
        rows.append(
            _comparison_row(
                year=1962,
                flow=flow,
                concept=concept,
                source_a_value=_as_float(audit_row["world_value_usd"]),
                source_b_original_value=_ine_pte_value(ine_row),
                valuation_basis=str(ine_row["valuation_basis"]),
                territorial_definition_a=str(audit_row["territorial_definition_status"]),
                territorial_definition_b=str(ine_row["territorial_definition"]),
                status="unresolved",
                explanation=(
                    "World totals are numerically close after a diagnostic 28.75 PTE/USD "
                    "conversion, but the exchange-rate source and Comtrade reporter "
                    "territorial definition are not yet independently documented."
                ),
                evidence_reference=(
                    f"INE Volume I PDF page {ine_row['page_number']} "
                    f"({ine_row['table_title']}); "
                    "results/diagnostics/comtrade_coverage/comtrade_coverage_audit.csv "
                    f"1962 {flow} World row."
                ),
            )
        )

    memberships = _colonial_memberships_1962(root)
    expected_entities = (
        sorted(set(memberships["entity_id"].astype(str))) if not memberships.empty else []
    )
    for flow, concept in (("X", "Overseas exports"), ("M", "Overseas imports")):
        ine_row = _ine_aggregate_row(ine, flow=flow, partner_group="Ultramar")
        if ine_row is None:
            continue
        observed = _observed_colonial_comtrade(matrix, memberships, flow=flow)
        observed_entities = (
            sorted(set(observed["entity_id"].astype(str))) if not observed.empty else []
        )
        missing_entities = sorted(set(expected_entities).difference(observed_entities))
        source_a_value = (
            float(pd.to_numeric(observed["trade_value_usd"], errors="coerce").sum())
            if not observed.empty
            else pd.NA
        )
        rows.append(
            _comparison_row(
                year=1962,
                flow=flow,
                concept=concept,
                source_a_value=source_a_value,
                source_b_original_value=_ine_pte_value(ine_row),
                valuation_basis=str(ine_row["valuation_basis"]),
                territorial_definition_a=(
                    "Observed Comtrade colonial partner subset; missing partners remain unresolved."
                ),
                territorial_definition_b=str(ine_row["territorial_definition"]),
                status="unresolved",
                explanation=(
                    "Comtrade colonial total is an observed lower bound because not all "
                    "configured overseas entities returned in the 1962 local snapshot."
                ),
                evidence_reference=(
                    f"INE Volume I PDF page {ine_row['page_number']} "
                    f"({ine_row['table_title']}); "
                    "data/interim/live/comtrade_coverage_matrix.csv 1962 S1 colonial "
                    "partner rows; config/historical_groups.yml colonies group."
                ),
                expected_partner_count=len(expected_entities),
                observed_partner_count=len(observed_entities),
                missing_partner_entities=";".join(missing_entities),
            )
        )
    return pd.DataFrame.from_records(rows, columns=INE_COMTRADE_1962_COLUMNS)


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


def build_ine_comtrade_1962_notes(reconciliation: pd.DataFrame) -> str:
    """Summarise the 1962 INE-Comtrade reconciliation result."""

    unresolved = int(reconciliation["reconciliation_status"].ne("reconciled").sum())
    world = reconciliation.loc[reconciliation["concept"].str.startswith("World", na=False)]
    overseas = reconciliation.loc[reconciliation["concept"].str.startswith("Overseas", na=False)]
    lines = [
        "1962 INE and UN Comtrade reconciliation",
        "=======================================",
        "",
        f"Comparison rows: {len(reconciliation)}",
        f"Unresolved rows: {unresolved}",
        "",
        "Conversion diagnostic",
        "---------------------",
        (
            "INE escudo values are divided by 28.75 PTE/USD only as a diagnostic "
            "conversion because no exchange-rate source has been registered yet."
        ),
    ]
    if not world.empty:
        max_world_relative = float(
            pd.to_numeric(world["relative_difference"], errors="coerce").abs().max()
        )
        lines.append(
            f"Maximum World relative difference after diagnostic conversion: "
            f"{max_world_relative:.8f}"
        )
    if not overseas.empty:
        min_coverage = float(pd.to_numeric(overseas["coverage_ratio"], errors="coerce").min())
        lines.extend(
            [
                "",
                "Overseas comparison",
                "-------------------",
                (
                    "Comtrade overseas partner sums remain lower bounds until missing "
                    "partner records are resolved."
                ),
                f"Minimum observed overseas partner coverage ratio: {min_coverage:.6f}",
            ]
        )
    lines.extend(
        [
            "",
            "Status",
            "------",
            (
                "1962 is not marked reconciled. Numerical closeness is insufficient "
                "until reporter territory, valuation treatment, and the exchange-rate "
                "source are independently documented."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def build_trade_reconciliation_notes(comparison: pd.DataFrame) -> str:
    """Write concise notes about source coverage and unresolved gaps."""

    missing = comparison.loc[comparison["confidence_status"] == "missing_source", "source"].unique()
    return "\n".join(
        [
            "Trade source reconciliation",
            "===========================",
            "",
            "Rows are source-preserving. Conflicting totals are not averaged.",
            "UN Comtrade World partner totals are used only as the current benchmark.",
            "Validated 1962 INE aggregates are included with a diagnostic conversion;",
            "OECD, EFTA, and CEPII structured totals are not available locally yet.",
            "",
            (
                "Sources with at least one missing structured row: "
                f"{', '.join(sorted(str(item) for item in missing))}"
            ),
            "",
        ]
    )


def build_reconciliation_registry(ine_comtrade_1962: pd.DataFrame) -> pd.DataFrame:
    """Build a small registry of source-pair reconciliation readiness."""

    if ine_comtrade_1962.empty:
        return pd.DataFrame.from_records(
            [
                {
                    "reconciliation_id": "ine_comtrade_1962",
                    "benchmark_year": 1962,
                    "source_a": "UN Comtrade",
                    "source_b": "INE",
                    "row_count": 0,
                    "reconciled_row_count": 0,
                    "unresolved_row_count": 0,
                    "overall_status": "not_available",
                    "blocking_reasons": "missing_local_ine_or_comtrade_inputs",
                    "evidence_reference": "",
                }
            ],
            columns=RECONCILIATION_REGISTRY_COLUMNS,
        )
    unresolved = ine_comtrade_1962.loc[
        ~ine_comtrade_1962["reconciliation_status"].isin(
            ["reconciled", "reconciled_with_conversion"]
        )
    ]
    reasons = [
        "exchange_rate_source_not_registered",
        "comtrade_reporter_territory_unresolved",
    ]
    if (pd.to_numeric(ine_comtrade_1962["coverage_ratio"], errors="coerce") < 1.0).any():
        reasons.append("colonial_partner_coverage_incomplete")
    return pd.DataFrame.from_records(
        [
            {
                "reconciliation_id": "ine_comtrade_1962",
                "benchmark_year": 1962,
                "source_a": "UN Comtrade",
                "source_b": "INE",
                "row_count": len(ine_comtrade_1962),
                "reconciled_row_count": len(ine_comtrade_1962) - len(unresolved),
                "unresolved_row_count": len(unresolved),
                "overall_status": "unresolved" if not unresolved.empty else "reconciled",
                "blocking_reasons": ";".join(reasons) if not unresolved.empty else "",
                "evidence_reference": (
                    "data/interim/live/ine_comtrade_1962_reconciliation.csv; "
                    "results/diagnostics/reconciliation/"
                    "ine_comtrade_1962_reconciliation.txt"
                ),
            }
        ],
        columns=RECONCILIATION_REGISTRY_COLUMNS,
    )


def _as_int(value: Any) -> int:
    return int(str(value))


def _load_ine_1962_aggregates(root: Path) -> pd.DataFrame:
    path = root / "data/processed/live/ine_1962_aggregate_trade_harmonised.csv"
    frame = _read_optional_csv(path)
    if frame.empty:
        return frame
    if "adjudication_status" not in frame:
        return pd.DataFrame(columns=frame.columns)
    return frame.loc[frame["adjudication_status"].eq("double_entry_verified")].copy()


def _read_optional_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def _ine_aggregate_row(
    ine: pd.DataFrame, *, flow: str, partner_group: str
) -> dict[str, object] | None:
    rows = ine.loc[ine["flow"].eq(flow) & ine["partner_group_source"].eq(partner_group)]
    if rows.empty:
        return None
    return cast(dict[str, object], rows.iloc[0].to_dict())


def _comtrade_world_row(audit: pd.DataFrame, *, flow: str) -> dict[str, object] | None:
    rows = audit.loc[audit["year"].eq(1962) & audit["flow_code"].eq(flow)]
    if rows.empty:
        return None
    return cast(dict[str, object], rows.iloc[0].to_dict())


def _ine_pte_value(row: dict[str, object]) -> float:
    return _as_float(row["value_source"]) * _as_float(row["unit_multiplier"])


def _as_float(value: object) -> float:
    if isinstance(value, int | float):
        return float(value)
    return float(str(value))


def _comparison_row(
    *,
    year: int,
    flow: str,
    concept: str,
    source_a_value: object,
    source_b_original_value: float,
    valuation_basis: str,
    territorial_definition_a: str,
    territorial_definition_b: str,
    status: str,
    explanation: str,
    evidence_reference: str,
    expected_partner_count: int | None = None,
    observed_partner_count: int | None = None,
    missing_partner_entities: str = "",
) -> dict[str, object]:
    source_b_value = source_b_original_value / PTE_PER_USD_DIAGNOSTIC_1962
    source_a_numeric = pd.to_numeric(pd.Series([source_a_value]), errors="coerce").iloc[0]
    signed_difference: object
    if pd.notna(source_a_numeric):
        signed_difference = float(source_a_numeric) - source_b_value
        absolute_difference: object = abs(signed_difference)
        relative_difference: object = (
            signed_difference / source_b_value if source_b_value else pd.NA
        )
    else:
        signed_difference = pd.NA
        absolute_difference = pd.NA
        relative_difference = pd.NA
    coverage_ratio: object = pd.NA
    if expected_partner_count is not None and observed_partner_count is not None:
        coverage_ratio = (
            observed_partner_count / expected_partner_count if expected_partner_count else pd.NA
        )
    return {
        "year": year,
        "flow": flow,
        "concept": concept,
        "source_a": "UN Comtrade",
        "source_b": "INE",
        "source_a_value": source_a_value,
        "source_b_value": source_b_value,
        "absolute_difference": absolute_difference,
        "relative_difference": relative_difference,
        "unit": "USD",
        "valuation_basis": valuation_basis,
        "territorial_definition_a": territorial_definition_a,
        "territorial_definition_b": territorial_definition_b,
        "reconciliation_status": status,
        "explanation": explanation,
        "evidence_reference": evidence_reference,
        "signed_difference": signed_difference,
        "relative_difference_denominator": "source_b_value_converted_to_USD",
        "source_a_original_value": source_a_value,
        "source_a_currency": "USD",
        "source_b_original_value": source_b_original_value,
        "source_b_currency": "PTE",
        "conversion_method": (
            "source_b_original_value / 28.75; diagnostic fixed PTE/USD conversion, "
            "exchange-rate source not registered"
        ),
        "expected_partner_count": expected_partner_count
        if expected_partner_count is not None
        else pd.NA,
        "observed_partner_count": observed_partner_count
        if observed_partner_count is not None
        else pd.NA,
        "coverage_ratio": coverage_ratio,
        "missing_partner_entities": missing_partner_entities,
    }


def _colonial_memberships_1962(root: Path) -> pd.DataFrame:
    group_path = root / "config/historical_groups.yml"
    area_path = root / "config/comtrade_partner_areas.yml"
    if not group_path.exists() or not area_path.exists():
        return pd.DataFrame()
    memberships = load_historical_group_memberships(group_path, area_path)
    return memberships.loc[
        memberships["year"].eq(1962) & memberships["partner_group"].eq("colonies")
    ].copy()


def _observed_colonial_comtrade(
    matrix: pd.DataFrame, memberships: pd.DataFrame, *, flow: str
) -> pd.DataFrame:
    if matrix.empty or memberships.empty:
        return pd.DataFrame()
    colonial_entities = set(memberships["entity_id"].astype(str))
    return matrix.loc[
        matrix["year"].eq(1962)
        & matrix["flow_code"].eq(flow)
        & matrix["classification_code"].eq("S1")
        & matrix["entity_id"].astype(str).isin(colonial_entities)
        & matrix["trade_value_usd"].notna()
    ].copy()
