"""Guarded EFTA policy and tariff dataset scaffolding."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

POLICY_SOURCE_COLUMNS = [
    "source_id",
    "source_title",
    "issuing_institution",
    "publication_year",
    "source_type",
    "url_or_catalogue_reference",
    "local_filename",
    "sha256",
    "licence",
    "access_conditions",
    "registration_status",
    "notes",
]

TARIFF_POLICY_COLUMNS = [
    "year",
    "source_classification",
    "commodity_code",
    "commodity_description",
    "product_group",
    "tariff_before",
    "tariff_after",
    "scheduled_reduction",
    "actual_reduction",
    "exception_status",
    "portuguese_special_treatment_status",
    "quota_restriction_status",
    "source_id",
    "page",
    "table",
    "notes",
    "estimate_status",
]

POLICY_PRODUCT_MAPPING_COLUMNS = [
    "policy_year",
    "policy_product_code",
    "policy_product_description",
    "trade_source_classification",
    "trade_commodity_code",
    "trade_commodity_description",
    "mapping_method",
    "mapping_confidence",
    "evidence_source",
    "notes",
]

POLICY_COVERAGE_COLUMNS = [
    "dataset",
    "required",
    "available",
    "coverage_ratio",
    "status",
    "blocking_reason",
]

POLICY_STATUS_COLUMNS = [
    "status",
    "readiness_audit_status",
    "policy_rows",
    "source_rows",
    "product_mapping_rows",
    "blocking_reason",
]


def build_efta_policy_outputs(
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """Build blocked EFTA policy/tariff outputs unless empirical prerequisites pass."""

    audit = _read_csv(root / "results/live/empirical_readiness_audit.csv")
    audit_status, audit_reasons = _audit_gate(audit)
    sources = build_efta_policy_source_registry(audit_status, audit_reasons)
    policy = pd.DataFrame(columns=TARIFF_POLICY_COLUMNS)
    product_mapping = pd.DataFrame(columns=POLICY_PRODUCT_MAPPING_COLUMNS)
    coverage = build_efta_policy_coverage(sources, policy, product_mapping, audit_status)
    status = build_efta_policy_status(sources, policy, product_mapping, audit_status, audit_reasons)
    notes = build_efta_policy_notes(status, coverage)
    return sources, policy, product_mapping, coverage, status, notes


def build_efta_policy_source_registry(audit_status: str, audit_reasons: list[str]) -> pd.DataFrame:
    """Register the intended source class without claiming source acquisition."""

    return pd.DataFrame.from_records(
        [
            {
                "source_id": "efta_annual_reports",
                "source_title": "EFTA annual reports and convention/tariff materials",
                "issuing_institution": "European Free Trade Association",
                "publication_year": pd.NA,
                "source_type": "policy_source_class",
                "url_or_catalogue_reference": "https://www.efta.int/media-resources/publications",
                "local_filename": "",
                "sha256": "",
                "licence": "to_be_confirmed_before_local_preservation",
                "access_conditions": "not_acquired_because_empirical_prerequisites_blocked",
                "registration_status": "blocked"
                if audit_status != "ready"
                else "pending_acquisition",
                "notes": ";".join(audit_reasons),
            }
        ],
        columns=POLICY_SOURCE_COLUMNS,
    )


def build_efta_policy_coverage(
    sources: pd.DataFrame,
    policy: pd.DataFrame,
    product_mapping: pd.DataFrame,
    audit_status: str,
) -> pd.DataFrame:
    """Build policy-source, tariff-row, and product-mapping coverage diagnostics."""

    blocked_reason = (
        "empirical_readiness_audit_blocks_efta_policy_dataset"
        if audit_status != "ready"
        else "policy_sources_not_acquired"
    )
    records = [
        _coverage_record(
            "efta_policy_sources",
            1,
            int(sources["registration_status"].eq("acquired").sum()) if not sources.empty else 0,
            blocked_reason,
        ),
        _coverage_record("efta_tariff_policy_rows", 1, len(policy), blocked_reason),
        _coverage_record(
            "efta_policy_product_mapping",
            1,
            len(product_mapping),
            blocked_reason,
        ),
    ]
    return pd.DataFrame.from_records(records, columns=POLICY_COVERAGE_COLUMNS)


def build_efta_policy_status(
    sources: pd.DataFrame,
    policy: pd.DataFrame,
    product_mapping: pd.DataFrame,
    audit_status: str,
    audit_reasons: list[str],
) -> pd.DataFrame:
    """Summarise whether EFTA policy/tariff data can be built."""

    reasons = list(audit_reasons)
    if audit_status != "ready":
        reasons.append("empirical_readiness_audit_blocks_efta_policy_dataset")
    if policy.empty:
        reasons.append("efta_tariff_policy_rows_not_registered")
    if product_mapping.empty:
        reasons.append("efta_policy_product_mapping_not_registered")
    if sources.empty or not sources["registration_status"].eq("acquired").any():
        reasons.append("efta_policy_sources_not_acquired")
    unique_reasons = sorted(set(reason for reason in reasons if reason))
    return pd.DataFrame.from_records(
        [
            {
                "status": "ready" if not unique_reasons else "blocked",
                "readiness_audit_status": audit_status,
                "policy_rows": len(policy),
                "source_rows": len(sources),
                "product_mapping_rows": len(product_mapping),
                "blocking_reason": ";".join(unique_reasons),
            }
        ],
        columns=POLICY_STATUS_COLUMNS,
    )


def build_efta_policy_notes(status: pd.DataFrame, coverage: pd.DataFrame) -> str:
    """Build a human-readable blocked EFTA policy report."""

    row = {str(key): value for key, value in status.iloc[0].items()} if not status.empty else {}
    return "\n".join(
        [
            "EFTA policy and tariff dataset readiness",
            "========================================",
            "",
            f"Status: {row.get('status', 'unknown')}",
            f"Readiness audit status: {row.get('readiness_audit_status', 'unknown')}",
            f"Blocking reason: {row.get('blocking_reason', '')}",
            f"Policy rows: {row.get('policy_rows', 0)}",
            f"Source rows: {row.get('source_rows', 0)}",
            f"Product mapping rows: {row.get('product_mapping_rows', 0)}",
            f"Coverage rows: {len(coverage)}",
            "",
            "No tariff rates, reduction schedules, or policy exposure variables are inferred.",
            "EFTA policy data remain blocked until product-level exposure is analytically",
            "viable and source documents can be acquired, preserved, and mapped.",
            "",
        ]
    )


def _audit_gate(audit: pd.DataFrame) -> tuple[str, list[str]]:
    if audit.empty:
        return "missing", ["empirical_readiness_audit_missing"]
    required = {
        "product_level_coverage",
        "product_to_industry_mapping_coverage",
        "usable_industries",
        "usable_years",
        "classification_breaks_documented",
        "identification_variables_available",
    }
    relevant = audit.loc[audit["requirement"].astype(str).isin(required)]
    blocked = relevant.loc[~relevant["status"].astype(str).eq("satisfied")]
    if blocked.empty and len(relevant) == len(required):
        return "ready", []
    reasons = [
        f"{row['requirement']}={row['blocking_reason']}"
        for row in blocked.to_dict(orient="records")
    ]
    missing = sorted(required.difference(set(relevant["requirement"].astype(str))))
    reasons.extend(
        f"{requirement}=missing_from_empirical_readiness_audit" for requirement in missing
    )
    return "blocked", reasons


def _coverage_record(
    dataset: str, required: int, available: int, blocking_reason: str
) -> dict[str, object]:
    coverage_ratio = available / required if required else 0.0
    status = "available" if required and coverage_ratio >= 1.0 else "blocked"
    return {
        "dataset": dataset,
        "required": required,
        "available": available,
        "coverage_ratio": coverage_ratio,
        "status": status,
        "blocking_reason": "" if status == "available" else blocking_reason,
    }


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)
