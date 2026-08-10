"""Empirical-design preparation without causal claims."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from portugal_external_growth.config import load_yaml

PREREQUISITES = [
    "reviewed_bilateral_trade_panel",
    "stable_product_classification",
    "portuguese_sectoral_output_data",
    "documented_product_to_industry_mapping",
    "sufficient_observations_and_variation",
    "simultaneity_and_common_shock_strategy",
]

PREREQUISITE_AUDIT_REQUIREMENTS = {
    "reviewed_bilateral_trade_panel": (
        "annual_trade_coverage",
        "colonial_partner_completeness",
        "european_partner_completeness",
        "territorial_consistency",
        "cross_source_reconciliation",
    ),
    "stable_product_classification": (
        "product_level_coverage",
        "classification_breaks_documented",
    ),
    "portuguese_sectoral_output_data": (
        "sectoral_output_coverage",
        "price_deflator_coverage",
    ),
    "documented_product_to_industry_mapping": (
        "product_to_industry_mapping_coverage",
        "classification_breaks_documented",
    ),
    "sufficient_observations_and_variation": (
        "usable_industries",
        "usable_years",
        "missingness_structure_documented",
        "identification_variables_available",
        "within_sector_exposure_variation",
        "within_year_cross_sectional_variation",
        "fixed_effect_residual_design_rank",
        "observation_parameter_ratio",
        "independent_cluster_count",
    ),
}

MODEL_AUDIT_REQUIREMENTS = {
    "shift_share_external_demand": (
        "annual_trade_coverage",
        "colonial_partner_completeness",
        "european_partner_completeness",
        "product_level_coverage",
        "product_to_industry_mapping_coverage",
        "sectoral_output_coverage",
        "price_deflator_coverage",
        "usable_industries",
        "usable_years",
        "missingness_structure_documented",
        "classification_breaks_documented",
        "identification_variables_available",
        "within_sector_exposure_variation",
        "within_year_cross_sectional_variation",
        "fixed_effect_residual_design_rank",
        "observation_parameter_ratio",
        "independent_cluster_count",
    ),
    "sector_year_fixed_effects": (
        "annual_trade_coverage",
        "colonial_partner_completeness",
        "european_partner_completeness",
        "sectoral_output_coverage",
        "price_deflator_coverage",
        "usable_industries",
        "usable_years",
        "identification_variables_available",
        "within_year_cross_sectional_variation",
        "fixed_effect_residual_design_rank",
        "observation_parameter_ratio",
        "independent_cluster_count",
    ),
    "efta_tariff_exposure": (
        "annual_trade_coverage",
        "european_partner_completeness",
        "product_level_coverage",
        "product_to_industry_mapping_coverage",
        "sectoral_output_coverage",
        "price_deflator_coverage",
        "classification_breaks_documented",
        "efta_policy_tariff_data_availability",
        "identification_variables_available",
        "within_year_cross_sectional_variation",
        "fixed_effect_residual_design_rank",
        "observation_parameter_ratio",
        "independent_cluster_count",
    ),
    "colonial_demand_shifters": (
        "annual_trade_coverage",
        "colonial_partner_completeness",
        "product_level_coverage",
        "product_to_industry_mapping_coverage",
        "sectoral_output_coverage",
        "price_deflator_coverage",
        "classification_breaks_documented",
        "external_demand_shifter_availability",
        "commodity_price_control_availability",
        "identification_variables_available",
        "within_sector_exposure_variation",
        "within_year_cross_sectional_variation",
        "fixed_effect_residual_design_rank",
        "observation_parameter_ratio",
        "independent_cluster_count",
    ),
}

EMPIRICAL_AUDIT_COLUMNS = [
    "requirement",
    "required",
    "available",
    "coverage",
    "status",
    "blocking_reason",
]

RESOLVED_RECONCILIATION_STATUSES = {"reconciled", "satisfactory_with_caveats"}
RESOLVED_IDENTIFICATION_STATUSES = {"satisfied", "approved", "resolved"}
DEFAULT_TRADE_SAMPLE_YEARS = tuple(range(1962, 1974))
TRADE_SAMPLE_FLOWS = ("X", "M")
REQUIRED_RECONCILIATION_SCOPES = frozenset({"ine_comtrade", "cepii", "efta", "oecd"})
REQUIRED_RECONCILIATION_SCOPE_COUNT = len(REQUIRED_RECONCILIATION_SCOPES)
MIN_USABLE_INDUSTRIES = 10
MIN_INDEPENDENT_CLUSTERS = 10


def build_empirical_prerequisite_status(root: Path | None = None) -> pd.DataFrame:
    """Return the current empirical-design prerequisite status."""

    if root is None:
        return pd.DataFrame(
            [
                {
                    "prerequisite": prerequisite,
                    "status": "not_satisfied",
                    "blocking_reason": _blocking_reason(prerequisite),
                }
                for prerequisite in PREREQUISITES
            ]
        )

    audit = build_empirical_readiness_audit(root)
    return pd.DataFrame(
        [_prerequisite_record(root, audit, prerequisite) for prerequisite in PREREQUISITES]
    )


def load_empirical_design_matrix_or_empty(root: Path) -> pd.DataFrame:
    """Return an existing empirical design matrix instead of overwriting it with a scaffold."""

    path = root / "data/interim/live/empirical_design_matrix.csv"
    existing = _read_csv(path)
    required_columns = set(empty_design_matrix().columns) - {"source_quality"}
    if not existing.empty and required_columns.issubset(existing.columns):
        return existing
    return empty_design_matrix()


def build_empirical_readiness_audit(root: Path) -> pd.DataFrame:
    """Build a requirement-level empirical-readiness audit matrix."""

    records = [
        _annual_trade_coverage(root),
        _colonial_partner_completeness(root),
        _european_partner_completeness(root),
        _product_level_coverage(root),
        _product_industry_mapping_coverage(root),
        _sectoral_output_coverage(root),
        _deflator_coverage(root),
        _territorial_consistency(root),
        _cross_source_reconciliation(root),
        _efta_policy_availability(root),
        _external_demand_shifter_availability(root),
        _commodity_price_control_availability(root),
        _usable_industries(root),
        _usable_years(root),
        _missingness_structure(root),
        _classification_breaks(root),
        _identification_variables(root),
        _within_sector_exposure_variation(root),
        _within_year_cross_sectional_variation(root),
        _fixed_effect_residual_design_rank(root),
        _observation_parameter_ratio(root),
        _independent_cluster_count(root),
    ]
    return pd.DataFrame.from_records(records, columns=EMPIRICAL_AUDIT_COLUMNS)


def build_empirical_readiness_audit_notes(audit: pd.DataFrame) -> str:
    """Build a human-readable empirical-readiness audit report."""

    blocked = audit.loc[~audit["status"].eq("satisfied")]
    return "\n".join(
        [
            "Empirical-design readiness audit",
            "================================",
            "",
            f"Requirements checked: {len(audit)}",
            f"Satisfied requirements: {int(audit['status'].eq('satisfied').sum())}",
            f"Blocked requirements: {len(blocked)}",
            "",
            "No causal regressions, tariff effects, or fitted model coefficients are produced.",
            "The repository remains blocked for empirical estimation until every required",
            "coverage and reconciliation row is satisfied by source-grounded evidence.",
            "",
            "Blocking reasons:",
            *[
                f"- {row['requirement']}: {row['blocking_reason']}"
                for row in blocked.to_dict(orient="records")
            ],
            "",
        ]
    )


def build_model_specification_registry(root: Path | None = None) -> pd.DataFrame:
    """Create a registry of candidate model families without fitting them."""

    records = [
        _model_record(
            root=root,
            model_slug="shift_share_external_demand",
            model_family="shift_share_exposure",
            unit_of_observation="sector_year",
            dependent_variable="sectoral_output_growth",
            identification_risk="Requires stable sector-output panel and exposure shares.",
        ),
        _model_record(
            root=root,
            model_slug="sector_year_fixed_effects",
            model_family="fixed_effects_panel",
            unit_of_observation="sector_year",
            dependent_variable="sectoral_output_growth",
            identification_risk="Common European growth shocks require explicit controls.",
        ),
        _model_record(
            root=root,
            model_slug="efta_tariff_exposure",
            model_family="tariff_exposure_design",
            unit_of_observation="sector_year",
            dependent_variable="sectoral_export_or_output_growth",
            identification_risk="Requires documented EFTA tariff schedules.",
        ),
        _model_record(
            root=root,
            model_slug="colonial_demand_shifters",
            model_family="external_demand_shift_design",
            unit_of_observation="sector_year",
            dependent_variable="sectoral_export_or_output_growth",
            identification_risk="Commodity price channels must be controlled directly.",
        ),
    ]
    return pd.DataFrame.from_records(records)


def _model_record(
    *,
    root: Path | None,
    model_slug: str,
    model_family: str,
    unit_of_observation: str,
    dependent_variable: str,
    identification_risk: str,
) -> dict[str, object]:
    requirements = MODEL_AUDIT_REQUIREMENTS[model_slug]
    status = "blocked_pending_prerequisites"
    blocking_requirements = "empirical_readiness_audit_not_evaluated"
    if root is not None:
        audit = build_empirical_readiness_audit(root)
        rows = audit.loc[audit["requirement"].isin(requirements)]
        blocked = rows.loc[~rows["status"].eq("satisfied")]
        missing = sorted(set(requirements).difference(set(rows["requirement"])))
        if blocked.empty and not missing:
            status = "ready"
            blocking_requirements = ""
        else:
            blocking_requirements = ";".join(
                [
                    *[
                        f"{row['requirement']}={row['blocking_reason']}"
                        for row in blocked.to_dict(orient="records")
                    ],
                    *[
                        f"{requirement}=missing_from_empirical_readiness_audit"
                        for requirement in missing
                    ],
                ]
            )
    return {
        "model_slug": model_slug,
        "model_family": model_family,
        "unit_of_observation": unit_of_observation,
        "dependent_variable": dependent_variable,
        "status": status,
        "required_audit_requirements": ";".join(requirements),
        "blocking_requirements": blocking_requirements,
        "identification_risk": identification_risk,
    }


def empty_design_matrix() -> pd.DataFrame:
    """Return a schema-stable empty design matrix."""

    return pd.DataFrame(
        columns=[
            "sector_code",
            "year",
            "outcome_variable",
            "colonial_exposure",
            "european_exposure",
            "controls_available",
            "source_quality",
        ]
    )


def empty_diagnostics() -> pd.DataFrame:
    """Return schema-stable diagnostics showing models are not fit yet."""

    return pd.DataFrame(
        [
            {
                "diagnostic": "minimum_prerequisites",
                "status": "failed",
                "value": 0,
                "note": "Design matrix is intentionally empty until prerequisites are satisfied.",
            }
        ]
    )


def empty_coefficients() -> pd.DataFrame:
    """Return an empty coefficient table schema."""

    return pd.DataFrame(
        columns=[
            "model_slug",
            "term",
            "estimate",
            "standard_error",
            "p_value",
            "confidence_interval_low",
            "confidence_interval_high",
            "status",
        ]
    )


def empty_identification_strategy_review() -> pd.DataFrame:
    """Return a machine-readable scaffold for identification-risk review."""

    return pd.DataFrame(
        [
            {
                "strategy_component": "simultaneity",
                "status": "blocked",
                "blocking_reason": "No source-grounded simultaneity strategy is registered.",
            },
            {
                "strategy_component": "common_european_shocks",
                "status": "blocked",
                "blocking_reason": (
                    "Common-shock controls and sensitivity checks are not specified."
                ),
            },
        ]
    )


def build_empirical_risk_notes() -> str:
    """Document assumptions and identification risks before model fitting."""

    return "\n".join(
        [
            "Empirical extension readiness",
            "=============================",
            "",
            "No model has been fit and no causal coefficient is reported.",
            "The current repository lacks a reviewed bilateral trade panel, stable",
            "product-to-industry mapping, Portuguese sectoral output data, and",
            "documented treatment of simultaneity and common European shocks.",
            "",
            "Prohibited shortcuts remain blocked: aggregate fourteen-observation",
            "regressions, machine-learning prediction models, gross-export-to-GDP",
            "equivalence, and single preferred specifications without sensitivity",
            "analysis.",
            "",
        ]
    )


def _blocking_reason(prerequisite: str) -> str:
    reasons = {
        "reviewed_bilateral_trade_panel": (
            "Comtrade coverage and source reconciliation are incomplete."
        ),
        "stable_product_classification": (
            "Only aggregate TOTAL records are currently available locally."
        ),
        "portuguese_sectoral_output_data": (
            "No reviewed 1960-1973 sectoral output panel is registered."
        ),
        "documented_product_to_industry_mapping": "No official correspondence table is registered.",
        "sufficient_observations_and_variation": "Design matrix has not been constructed.",
        "simultaneity_and_common_shock_strategy": "Identification controls are not specified yet.",
    }
    return reasons[prerequisite]


def _annual_trade_coverage(root: Path) -> dict[str, object]:
    frame = _read_csv(
        root / "data/processed/live/validated_annual_aggregate_external_orientation.csv"
    )
    required = _trade_year_flow_requirement(root)
    if frame.empty:
        return _record("annual_trade_coverage", required, 0, "annual_aggregate_dataset_missing")
    if {"year", "flow_code"}.issubset(frame.columns):
        available = _available_year_flow_pairs(frame, root=root)
    else:
        sample = _sample_year_rows(frame, root=root)
        available = int(
            sample.get("world_exports_pte", pd.Series(dtype=float)).notna().sum()
        ) + int(sample.get("world_imports_pte", pd.Series(dtype=float)).notna().sum())
    return _record(
        "annual_trade_coverage",
        required,
        available,
        "annual year-flow aggregate trade coverage is incomplete",
    )


def _colonial_partner_completeness(root: Path) -> dict[str, object]:
    frame = _read_csv(
        root / "data/processed/live/validated_annual_aggregate_external_orientation.csv"
    )
    if frame.empty:
        return _record(
            "colonial_partner_completeness",
            _trade_year_flow_requirement(root),
            0,
            "colonial aggregate table missing",
        )
    required = _trade_year_flow_requirement(root)
    satisfied = _flow_specific_non_null_count(
        frame,
        export_columns=["colonial_exports_complete_pte"],
        import_columns=["colonial_imports_complete_pte"],
        root=root,
    )
    return _record(
        "colonial_partner_completeness",
        required,
        satisfied,
        "complete source-backed colonial aggregate coverage remains incomplete",
    )


def _european_partner_completeness(root: Path) -> dict[str, object]:
    frame = _read_csv(
        root / "data/processed/live/validated_annual_aggregate_external_orientation.csv"
    )
    if frame.empty:
        return _record(
            "european_partner_completeness",
            _trade_year_flow_requirement(root),
            0,
            "aggregate dataset missing",
        )
    required = _trade_year_flow_requirement(root)
    export_columns = ["fixed_europe_exports_pte"]
    import_columns = ["fixed_europe_imports_pte"]
    if not set(export_columns + import_columns).issubset(frame.columns):
        return _record(
            "european_partner_completeness",
            required,
            0,
            "fixed European partner-sample completeness status is not machine-readable",
        )
    available = _flow_specific_non_null_count(
        frame,
        export_columns=export_columns,
        import_columns=import_columns,
        root=root,
    )
    return _record(
        "european_partner_completeness",
        required,
        available,
        "fixed European partner-sample coverage is incomplete",
    )


def _product_level_coverage(root: Path) -> dict[str, object]:
    status = _read_csv(root / "results/live/comtrade_product_extraction_status.csv")
    if status.empty:
        return _record("product_level_coverage", 1, 0, "product extraction status missing")
    rows = int(status.get("normalised_rows", pd.Series([0])).iloc[0])
    blocking = str(status.get("blocking_reason", pd.Series(["product extraction blocked"])).iloc[0])
    return _record("product_level_coverage", 1, int(rows > 0), blocking or "product rows missing")


def _product_industry_mapping_coverage(root: Path) -> dict[str, object]:
    status = _read_csv(
        root / "results/diagnostics/product_industry_mapping/product_mapping_status.csv"
    )
    if status.empty:
        return _record(
            "product_to_industry_mapping_coverage", 1, 0, "product mapping status missing"
        )
    coverage = float(
        pd.to_numeric(status.get("max_mapping_coverage_share", pd.Series([0.0])), errors="coerce")
        .fillna(0.0)
        .iloc[0]
    )
    blocking = str(status.get("blocking_reason", pd.Series(["product mapping blocked"])).iloc[0])
    return _record(
        "product_to_industry_mapping_coverage",
        1,
        coverage,
        blocking or "product mapping coverage below one",
    )


def _sectoral_output_coverage(root: Path) -> dict[str, object]:
    dictionary = _read_csv(root / "results/live/bpstat_macro_data_dictionary.csv")
    if dictionary.empty:
        return _record("sectoral_output_coverage", 1, 0, "macro data dictionary missing")
    empirical = _empirical_use_mask(dictionary)
    if empirical is None:
        return _record(
            "sectoral_output_coverage",
            1,
            0,
            "macro data dictionary lacks machine-readable empirical-use review flags",
        )
    concept_text = dictionary.astype(str).agg(" ".join, axis=1).str.lower()
    candidate = concept_text.str.contains("sector|gva|manufacturing|industry", regex=True)
    available = int((candidate & empirical).sum() > 0)
    return _record(
        "sectoral_output_coverage",
        1,
        int(available > 0),
        "reviewed sectoral output panel is not enabled for empirical analysis",
    )


def _deflator_coverage(root: Path) -> dict[str, object]:
    dictionary = _read_csv(root / "results/live/bpstat_macro_data_dictionary.csv")
    if dictionary.empty:
        return _record("price_deflator_coverage", 1, 0, "macro data dictionary missing")
    empirical = _empirical_use_mask(dictionary)
    if empirical is None:
        return _record(
            "price_deflator_coverage",
            1,
            0,
            "macro data dictionary lacks machine-readable empirical-use review flags",
        )
    text = dictionary.astype(str).agg(" ".join, axis=1).str.lower()
    candidate = text.str.contains("deflator|price")
    available = int((candidate & empirical).sum() > 0)
    return _record(
        "price_deflator_coverage",
        1,
        available,
        "price/deflator series are not reviewed for sector-level empirical use",
    )


def _empirical_use_mask(dictionary: pd.DataFrame) -> pd.Series | None:
    if "analytical_use" not in dictionary.columns:
        return None
    analytical_use = dictionary["analytical_use"].astype(str).str.lower()
    excluded = analytical_use.str.contains(
        "context_only|not_usable|not_empirical|disabled|blocked",
        na=False,
    )
    return analytical_use.str.contains("empirical", na=False) & ~excluded


def _territorial_consistency(root: Path) -> dict[str, object]:
    audit = _read_csv(root / "results/diagnostics/comtrade_coverage/comtrade_coverage_audit.csv")
    if audit.empty:
        return _record(
            "territorial_consistency",
            _trade_year_flow_requirement(root),
            0,
            "territorial audit missing",
        )
    statuses = audit.get("territorial_definition_status", pd.Series(dtype=object)).astype(str)
    required = _trade_year_flow_requirement(root)
    resolved = audit.loc[statuses.eq("resolved")]
    if {"year", "flow_code"}.issubset(resolved.columns):
        available = _available_year_flow_pairs(resolved, root=root)
    else:
        available = int(resolved.shape[0])
    return _record(
        "territorial_consistency",
        required,
        available,
        "Comtrade reporter/partner territorial definitions remain unresolved",
    )


def _cross_source_reconciliation(root: Path) -> dict[str, object]:
    registry = _read_csv(root / "results/diagnostics/reconciliation/reconciliation_registry.csv")
    if registry.empty:
        return _record(
            "cross_source_reconciliation",
            REQUIRED_RECONCILIATION_SCOPE_COUNT,
            0,
            "reconciliation registry missing",
        )
    resolved = registry.loc[
        registry.get("overall_status", pd.Series(dtype=object))
        .astype(str)
        .isin(RESOLVED_RECONCILIATION_STATUSES)
    ]
    available_scopes = _reconciliation_scopes(resolved)
    return _record(
        "cross_source_reconciliation",
        REQUIRED_RECONCILIATION_SCOPE_COUNT,
        len(available_scopes & REQUIRED_RECONCILIATION_SCOPES),
        "INE-Comtrade, CEPII, EFTA, and OECD reconciliation scopes are not all resolved",
    )


def _reconciliation_scopes(frame: pd.DataFrame) -> set[str]:
    scopes: set[str] = set()
    for row in frame.to_dict(orient="records"):
        explicit = str(row.get("reconciliation_scope", "")).strip().lower()
        if explicit:
            scopes.add(_normalise_reconciliation_scope(explicit))
            continue
        text = " ".join(str(value) for value in row.values()).lower()
        scopes.add(_normalise_reconciliation_scope(text))
    return {scope for scope in scopes if scope}


def _normalise_reconciliation_scope(text: str) -> str:
    normalised = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    if "ine" in normalised and "comtrade" in normalised:
        return "ine_comtrade"
    for scope in ("cepii", "efta", "oecd"):
        if scope in normalised:
            return scope
    return normalised if normalised in REQUIRED_RECONCILIATION_SCOPES else ""


def _efta_policy_availability(root: Path) -> dict[str, object]:
    status = _read_csv(root / "results/diagnostics/efta_policy/efta_policy_status.csv")
    if not status.empty and "status" in status.columns:
        available = int(status["status"].astype(str).eq("ready").any())
        reason = str(
            status.get("blocking_reason", pd.Series(["EFTA policy dataset blocked"])).iloc[0]
        )
    else:
        policy = _read_csv(root / "data/interim/live/efta_policy_dataset.csv")
        available = int(not policy.empty)
        reason = "EFTA policy/tariff dataset is not registered"
    return _record(
        "efta_policy_tariff_data_availability",
        1,
        available,
        reason,
    )


def _external_demand_shifter_availability(root: Path) -> dict[str, object]:
    status = _read_csv(root / "results/diagnostics/external_demand_shifters/shifter_status.csv")
    if not status.empty and "status" in status.columns:
        available = int(status["status"].astype(str).eq("ready").any())
        reason = str(
            status.get("blocking_reason", pd.Series(["external demand shifters blocked"])).iloc[0]
        )
    else:
        available = 0
        reason = "external demand shifters are not registered"
    return _record("external_demand_shifter_availability", 1, available, reason)


def _commodity_price_control_availability(root: Path) -> dict[str, object]:
    status = _read_csv(root / "results/diagnostics/commodity_prices/control_status.csv")
    if not status.empty and "status" in status.columns:
        available = int(status["status"].astype(str).eq("ready").any())
        reason = str(
            status.get("blocking_reason", pd.Series(["commodity price controls blocked"])).iloc[0]
        )
    else:
        available = 0
        reason = "commodity price controls are not registered"
    return _record("commodity_price_control_availability", 1, available, reason)


def _usable_industries(root: Path) -> dict[str, object]:
    panel = _read_csv(root / "data/processed/live/industry_trade_panel.csv")
    if panel.empty:
        return _record(
            "usable_industries",
            MIN_USABLE_INDUSTRIES,
            0,
            "industry trade panel is empty",
        )
    available = int(panel.get("target_industry_code", pd.Series(dtype=object)).nunique())
    return _record(
        "usable_industries",
        MIN_USABLE_INDUSTRIES,
        available,
        f"fewer than {MIN_USABLE_INDUSTRIES} usable mapped industries are available",
    )


def _usable_years(root: Path) -> dict[str, object]:
    panel = _read_csv(root / "data/processed/live/industry_trade_panel.csv")
    if panel.empty:
        return _record("usable_years", 12, 0, "industry trade panel is empty")
    available = int(panel.get("year", pd.Series(dtype=object)).nunique())
    required = len(_trade_sample_years(root))
    return _record(
        "usable_years",
        required,
        available,
        "insufficient usable industry-panel years",
    )


def _missingness_structure(root: Path) -> dict[str, object]:
    diagnostics = _read_csv(
        root / "results/diagnostics/industry_exposure/industry_exposure_coverage.csv"
    )
    if diagnostics.empty:
        return _record(
            "missingness_structure_documented",
            1,
            0,
            "industry exposure coverage diagnostics missing",
        )
    available = int(diagnostics["status"].astype(str).eq("available").all())
    return _record(
        "missingness_structure_documented",
        1,
        available,
        "missingness structure remains dominated by blocked product/industry data",
    )


def _classification_breaks(root: Path) -> dict[str, object]:
    reasons: list[str] = []
    diagnostics = _read_csv(
        root / "results/diagnostics/comtrade_product/product_coverage_diagnostics.csv"
    )
    if diagnostics.empty:
        reasons.append("product classification coverage diagnostics missing or empty")
    else:
        classification = diagnostics.get("classification_code", pd.Series(dtype=object))
        classifications = classification.astype(str).str.strip()
        if classifications.empty or classifications.str.lower().isin({"", "nan", "none"}).all():
            reasons.append("product source classifications are not documented")
        original_rows = pd.to_numeric(
            diagnostics.get("original_classification_rows", pd.Series(dtype=object)),
            errors="coerce",
        ).fillna(0)
        if original_rows.empty or not bool((original_rows > 0).any()):
            reasons.append("original product-classification rows are not documented")

    mapping_status = _read_csv(
        root / "results/diagnostics/product_industry_mapping/product_mapping_status.csv"
    )
    status = (
        str(mapping_status.get("status", pd.Series(["missing"])).iloc[0])
        if not mapping_status.empty
        else "missing"
    )
    if status != "ready":
        reasons.append(f"product mapping status is {status}")

    mapping_config_path = root / "config/product_industry_mapping.yml"
    try:
        mapping_config = load_yaml(mapping_config_path) if mapping_config_path.exists() else {}
    except (OSError, TypeError, ValueError) as exc:
        mapping_config = {}
        reasons.append(f"product mapping configuration is unreadable: {exc}")
    mappings = mapping_config.get("mappings") if isinstance(mapping_config, dict) else None
    config_status = (
        str(mapping_config.get("mapping_status", "missing"))
        if isinstance(mapping_config, dict)
        else "missing"
    )
    if config_status.startswith("blocked") or not isinstance(mappings, list) or not mappings:
        reasons.append("source-grounded product classification mapping is not registered")

    documentation_path = root / "results/live/product_industry_mapping_documentation.txt"
    documentation = (
        documentation_path.read_text(encoding="utf-8").lower()
        if documentation_path.exists()
        else ""
    )
    blocked_markers = ("status: blocked", "remains empty", "not yet validated")
    if not documentation or any(marker in documentation for marker in blocked_markers):
        reasons.append("classification documentation is missing or blocked")

    available = int(not reasons)
    return _record(
        "classification_breaks_documented",
        1,
        available,
        ";".join(reasons) or "stable historical product classification documentation is incomplete",
    )


def _identification_variables(root: Path) -> dict[str, object]:
    design = _complete_design_matrix(root)
    if design.empty:
        return _record(
            "identification_variables_available",
            1,
            0,
            "empirical design matrix is empty or lacks sector/year exposure controls",
        )
    colonial = pd.to_numeric(design["colonial_exposure"], errors="coerce")
    european = pd.to_numeric(design["european_exposure"], errors="coerce")
    controls = design["controls_available"].astype("boolean")
    available = int(
        colonial.notna().all()
        and european.notna().all()
        and controls.notna().all()
        and bool(controls.all())
        and colonial.nunique(dropna=True) > 1
        and european.nunique(dropna=True) > 1
    )
    return _record(
        "identification_variables_available",
        1,
        available,
        "exposure and control variables are missing, incomplete, or non-varying",
    )


def _within_sector_exposure_variation(root: Path) -> dict[str, object]:
    design = _complete_design_matrix(root)
    if design.empty:
        return _record(
            "within_sector_exposure_variation",
            MIN_USABLE_INDUSTRIES,
            0,
            "empirical design matrix is empty or lacks sector/year exposure controls",
        )
    varying = 0
    for _sector, sector_rows in design.groupby("sector_code"):
        colonial_values = pd.to_numeric(sector_rows["colonial_exposure"], errors="coerce")
        european_values = pd.to_numeric(sector_rows["european_exposure"], errors="coerce")
        if colonial_values.nunique(dropna=True) > 1 and european_values.nunique(dropna=True) > 1:
            varying += 1
    return _record(
        "within_sector_exposure_variation",
        MIN_USABLE_INDUSTRIES,
        varying,
        "too few sectors have within-sector exposure variation over time",
    )


def _within_year_cross_sectional_variation(root: Path) -> dict[str, object]:
    design = _complete_design_matrix(root)
    required = len(_trade_sample_years(root))
    if design.empty:
        return _record(
            "within_year_cross_sectional_variation",
            required,
            0,
            "empirical design matrix is empty or lacks sector/year exposure controls",
        )
    varying_years = 0
    for _year, year_rows in design.groupby("year"):
        colonial_values = pd.to_numeric(year_rows["colonial_exposure"], errors="coerce")
        european_values = pd.to_numeric(year_rows["european_exposure"], errors="coerce")
        if colonial_values.nunique(dropna=True) > 1 and european_values.nunique(dropna=True) > 1:
            varying_years += 1
    return _record(
        "within_year_cross_sectional_variation",
        required,
        varying_years,
        "exposures lack cross-sectional variation within every sample year",
    )


def _fixed_effect_residual_design_rank(root: Path) -> dict[str, object]:
    design = _complete_design_matrix(root)
    if design.empty:
        return _record(
            "fixed_effect_residual_design_rank",
            2,
            0,
            "empirical design matrix is empty or lacks sector/year exposure controls",
        )
    rank = _residual_exposure_rank(design)
    return _record(
        "fixed_effect_residual_design_rank",
        2,
        rank,
        "colonial and European exposures are collinear after sector and year effects",
    )


def _observation_parameter_ratio(root: Path) -> dict[str, object]:
    design = _complete_design_matrix(root)
    if design.empty:
        return _record(
            "observation_parameter_ratio",
            1,
            0,
            "empirical design matrix is empty or lacks sector/year exposure controls",
        )
    observations = len(design)
    sector_count = int(design["sector_code"].nunique())
    year_count = int(design["year"].nunique())
    estimated_parameters = 2 + max(sector_count - 1, 0) + max(year_count - 1, 0)
    required = estimated_parameters + 1
    return _record(
        "observation_parameter_ratio",
        required,
        observations,
        "observations do not exceed exposure and fixed-effect parameter count",
    )


def _independent_cluster_count(root: Path) -> dict[str, object]:
    design = _complete_design_matrix(root)
    if design.empty:
        return _record(
            "independent_cluster_count",
            MIN_INDEPENDENT_CLUSTERS,
            0,
            "empirical design matrix is empty or lacks sector/year exposure controls",
        )
    clusters = int(design["sector_code"].nunique())
    return _record(
        "independent_cluster_count",
        MIN_INDEPENDENT_CLUSTERS,
        clusters,
        f"fewer than {MIN_INDEPENDENT_CLUSTERS} independent sector clusters are available",
    )


def _complete_design_matrix(root: Path) -> pd.DataFrame:
    design = _read_csv(root / "data/interim/live/empirical_design_matrix.csv")
    required_columns = {
        "sector_code",
        "year",
        "colonial_exposure",
        "european_exposure",
        "controls_available",
    }
    if design.empty or not required_columns.issubset(design.columns):
        return pd.DataFrame()
    complete = design.copy()
    complete["year"] = pd.to_numeric(complete["year"], errors="coerce")
    complete["colonial_exposure"] = pd.to_numeric(complete["colonial_exposure"], errors="coerce")
    complete["european_exposure"] = pd.to_numeric(complete["european_exposure"], errors="coerce")
    complete["sector_code"] = complete["sector_code"].astype("string").fillna("").str.strip()
    complete = complete.loc[
        complete["sector_code"].ne("")
        & complete["year"].notna()
        & complete["colonial_exposure"].notna()
        & complete["european_exposure"].notna()
    ].copy()
    return complete


def _residual_exposure_rank(design: pd.DataFrame) -> int:
    exposure = design[["colonial_exposure", "european_exposure"]].astype(float).to_numpy()
    sectors = pd.get_dummies(design["sector_code"].astype(str), drop_first=False, dtype=float)
    years = pd.get_dummies(design["year"].astype(int).astype(str), drop_first=False, dtype=float)
    fixed_effects = pd.concat([sectors, years], axis=1).to_numpy(dtype=float)
    if fixed_effects.size == 0:
        return int(np.linalg.matrix_rank(exposure))
    combined_rank = int(np.linalg.matrix_rank(np.column_stack([fixed_effects, exposure])))
    fixed_effect_rank = int(np.linalg.matrix_rank(fixed_effects))
    return combined_rank - fixed_effect_rank


def _available_year_flow_pairs(frame: pd.DataFrame, *, root: Path) -> int:
    pairs = frame.loc[
        frame["year"].isin(_trade_sample_years(root))
        & frame["flow_code"].astype(str).isin(TRADE_SAMPLE_FLOWS),
        ["year", "flow_code"],
    ]
    return int(pairs.drop_duplicates().shape[0])


def _trade_sample_years(root: Path) -> tuple[int, ...]:
    config_path = root / "config/project.yml"
    if config_path.exists():
        try:
            payload = load_yaml(config_path)
        except (OSError, TypeError, ValueError):
            payload = {}
        project = payload.get("project") if isinstance(payload, dict) else {}
        if isinstance(project, dict):
            start = _as_optional_int(project.get("bilateral_trade_panel_start_year"))
            end = _as_optional_int(project.get("bilateral_trade_panel_end_year"))
            if start is not None and end is not None and start <= end:
                return tuple(range(start, end + 1))
    return DEFAULT_TRADE_SAMPLE_YEARS


def _trade_year_flow_requirement(root: Path) -> int:
    return len(_trade_sample_years(root)) * len(TRADE_SAMPLE_FLOWS)


def _sample_year_rows(frame: pd.DataFrame, *, root: Path) -> pd.DataFrame:
    if "year" not in frame.columns:
        return frame
    return frame.loc[frame["year"].isin(_trade_sample_years(root))]


def _flow_specific_non_null_count(
    frame: pd.DataFrame,
    *,
    export_columns: list[str],
    import_columns: list[str],
    root: Path,
) -> int:
    if {"year", "flow_code"}.issubset(frame.columns):
        sample = frame.loc[frame["year"].isin(_trade_sample_years(root))].copy()
        flow_code = sample["flow_code"].astype(str)
        export_columns = [column for column in export_columns if column in sample.columns]
        import_columns = [column for column in import_columns if column in sample.columns]
        exports = sample.loc[flow_code.eq("X"), ["year", *export_columns]]
        imports = sample.loc[flow_code.eq("M"), ["year", *import_columns]]
        export_count = _non_null_year_count(exports, export_columns)
        import_count = _non_null_year_count(imports, import_columns)
        return export_count + import_count
    sample = _sample_year_rows(frame, root=root)
    export_count = _non_null_year_count(sample, export_columns)
    import_count = _non_null_year_count(sample, import_columns)
    return export_count + import_count


def _non_null_year_count(frame: pd.DataFrame, columns: list[str]) -> int:
    available_columns = [column for column in columns if column in frame.columns]
    if not available_columns or frame.empty:
        return 0
    if "year" in frame.columns:
        present = frame.loc[frame[available_columns].notna().any(axis=1), ["year"]]
        return int(present.drop_duplicates().shape[0])
    return int(frame[available_columns].notna().any(axis=1).sum())


def _as_optional_int(value: object) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "<na>", "none"}:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _record(
    requirement: str, required: float, available: float, blocking_reason: str
) -> dict[str, object]:
    coverage = available / required if required else 0.0
    status = "satisfied" if required and coverage >= 1.0 else "blocked"
    return {
        "requirement": requirement,
        "required": required,
        "available": available,
        "coverage": coverage,
        "status": status,
        "blocking_reason": "" if status == "satisfied" else blocking_reason,
    }


def _prerequisite_record(root: Path, audit: pd.DataFrame, prerequisite: str) -> dict[str, object]:
    if prerequisite == "simultaneity_and_common_shock_strategy":
        satisfied, reason = _identification_strategy_review_status(root)
    else:
        requirements = PREREQUISITE_AUDIT_REQUIREMENTS[prerequisite]
        rows = audit.loc[audit["requirement"].isin(requirements)]
        blocked = rows.loc[~rows["status"].eq("satisfied")]
        satisfied = blocked.empty and set(requirements).issubset(set(rows["requirement"]))
        reason = ";".join(
            f"{row['requirement']}={row['blocking_reason']}"
            for row in blocked.to_dict(orient="records")
        )
    return {
        "prerequisite": prerequisite,
        "status": "satisfied" if satisfied else "not_satisfied",
        "blocking_reason": "" if satisfied else reason or _blocking_reason(prerequisite),
    }


def _identification_strategy_review_status(root: Path) -> tuple[bool, str]:
    review = _read_csv(root / "results/live/identification_strategy_review.csv")
    if review.empty or "status" not in review:
        return False, "machine-readable identification strategy review is missing"
    statuses = review["status"].astype(str)
    unresolved = review.loc[~statuses.isin(RESOLVED_IDENTIFICATION_STATUSES)]
    if unresolved.empty:
        return True, ""
    if "blocking_reason" in unresolved:
        reason = ";".join(unresolved["blocking_reason"].dropna().astype(str).tolist())
    else:
        reason = "identification strategy review is not fully resolved"
    return False, reason or "identification strategy review is not fully resolved"


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)
