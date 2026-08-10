"""Empirical-design preparation without causal claims."""

from __future__ import annotations

import re
from math import ceil
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
        "sectoral_output_source_registry",
        "sectoral_output_source_coverage",
        "real_output_coverage",
        "output_growth_coverage",
        "price_deflator_coverage",
        "outcome_source_provenance",
        "outcome_definition_consistency",
        "dependent_variable_coverage",
    ),
    "documented_product_to_industry_mapping": (
        "product_to_industry_mapping_coverage",
        "classification_breaks_documented",
    ),
    "sufficient_observations_and_variation": (
        "usable_industries",
        "usable_growth_years",
        "missingness_structure_documented",
        "dependent_variable_coverage",
        "identification_variables_available",
        "within_sector_exposure_variation",
        "within_year_cross_sectional_variation",
        "fixed_effect_residual_design_rank",
        "observation_parameter_ratio",
        "sector_year_uniqueness",
        "sector_year_grid_coverage",
        "minimum_sector_years_per_industry",
        "residual_degrees_of_freedom",
        "independent_cluster_count",
    ),
}

MODEL_REQUIRED_PREREQUISITES = {
    "shift_share_external_demand": tuple(PREREQUISITES),
    "sector_year_fixed_effects": tuple(PREREQUISITES),
    "efta_tariff_exposure": (
        "reviewed_bilateral_trade_panel",
        "stable_product_classification",
        "documented_product_to_industry_mapping",
        "sufficient_observations_and_variation",
        "simultaneity_and_common_shock_strategy",
    ),
    "colonial_demand_shifters": (
        "reviewed_bilateral_trade_panel",
        "stable_product_classification",
        "documented_product_to_industry_mapping",
        "sufficient_observations_and_variation",
        "simultaneity_and_common_shock_strategy",
    ),
}

MODEL_REQUIRED_OUTCOMES = {
    "shift_share_external_demand": "sectoral_output_growth",
    "sector_year_fixed_effects": "sectoral_output_growth",
    "efta_tariff_exposure": "sectoral_export_growth",
    "colonial_demand_shifters": "sectoral_export_growth",
}

MODEL_EXTRA_AUDIT_REQUIREMENTS = {
    "shift_share_external_demand": (),
    "sector_year_fixed_effects": (),
    "efta_tariff_exposure": ("efta_policy_tariff_data_availability",),
    "colonial_demand_shifters": (
        "external_demand_shifter_availability",
        "commodity_price_control_availability",
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
MIN_SECTOR_YEAR_GRID_COVERAGE = 0.8
MIN_YEARS_PER_SECTOR = 8
MIN_RESIDUAL_DEGREES_OF_FREEDOM = 20
DEPENDENT_VARIABLE_NAME = "sectoral_output_growth"
DEPENDENT_VARIABLE_SOURCE_FILE = "data/processed/live/sectoral_output_panel.csv"
DEPENDENT_VARIABLE_SOURCE_COLUMN = "output_growth"
OUTPUT_GROWTH_METHOD = "log_change"
OUTPUT_GROWTH_LAG_DEFINITION = "previous_year"
OUTPUT_GROWTH_SAMPLE_RULE = "growth_sample_excludes_first_trade_year_without_prior_level"
REVIEWED_SOURCE_QUALITIES = frozenset({"reviewed", "source_reviewed", "validated"})
RESOLVED_CLASSIFICATION_BREAK_STATUSES = frozenset(
    {"no_break", "reviewed_compatible", "harmonised", "resolved_with_caveat"}
)
PLACEHOLDER_METADATA_VALUES = frozenset({"unknown", "unreviewed", "blocked", "missing"})
REQUIRED_OUTPUT_METADATA_COLUMNS = (
    "source_classification",
    "source_sector_code",
    "harmonised_sector_code",
    "classification_version",
    "mapping_version",
    "unit",
    "currency",
    "price_basis",
    "deflator_base",
    "classification_break_status",
    "real_output_method",
    "growth_method",
    "lag_definition",
    "log_or_percent_change",
    "base_year",
)

SECTORAL_OUTPUT_SOURCE_REGISTRY_COLUMNS = [
    "source_id",
    "provider",
    "dataset_table",
    "source_reference",
    "source_file_or_url",
    "retrieval_date",
    "checksum_if_local",
    "years",
    "classification",
    "licence_status",
    "review_status",
]


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


def load_sectoral_output_panel_or_empty(root: Path) -> pd.DataFrame:
    """Return an existing sectoral-output panel instead of overwriting it with a scaffold."""

    path = root / "data/processed/live/sectoral_output_panel.csv"
    existing = _read_csv(path)
    required_columns = set(empty_sectoral_output_panel().columns)
    if not existing.empty and required_columns.issubset(existing.columns):
        return existing
    return empty_sectoral_output_panel()


def load_sectoral_output_source_registry_or_empty(root: Path) -> pd.DataFrame:
    """Return an existing sectoral-output source registry or a schema-stable scaffold."""

    path = root / "data/raw/live/sectoral_output/source_registry.csv"
    existing = _read_csv(path)
    required_columns = set(empty_sectoral_output_source_registry().columns)
    if not existing.empty and required_columns.issubset(existing.columns):
        return existing
    return empty_sectoral_output_source_registry()


def build_empirical_readiness_audit(root: Path) -> pd.DataFrame:
    """Build a requirement-level empirical-readiness audit matrix."""

    records = [
        _annual_trade_coverage(root),
        _colonial_partner_completeness(root),
        _european_partner_completeness(root),
        _product_level_coverage(root),
        _product_industry_mapping_coverage(root),
        _sectoral_output_source_registry(root),
        _sectoral_output_source_coverage(root),
        _real_output_coverage(root),
        _output_growth_coverage(root),
        _deflator_coverage(root),
        _outcome_source_provenance(root),
        _outcome_definition_consistency(root),
        _sectoral_export_growth_coverage(root),
        _territorial_consistency(root),
        _cross_source_reconciliation(root),
        _efta_policy_availability(root),
        _external_demand_shifter_availability(root),
        _commodity_price_control_availability(root),
        _usable_industries(root),
        _usable_years(root),
        _usable_growth_years(root),
        _missingness_structure(root),
        _classification_breaks(root),
        _dependent_variable_coverage(root),
        _identification_variables(root),
        _within_sector_exposure_variation(root),
        _within_year_cross_sectional_variation(root),
        _fixed_effect_residual_design_rank(root),
        _observation_parameter_ratio(root),
        _sector_year_uniqueness(root),
        _sector_year_grid_coverage(root),
        _minimum_sector_years_per_industry(root),
        _residual_degrees_of_freedom(root),
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
            dependent_variable="sectoral_export_growth",
            identification_risk="Requires documented EFTA tariff schedules.",
        ),
        _model_record(
            root=root,
            model_slug="colonial_demand_shifters",
            model_family="external_demand_shift_design",
            unit_of_observation="sector_year",
            dependent_variable="sectoral_export_growth",
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
    extra_requirements = MODEL_EXTRA_AUDIT_REQUIREMENTS[model_slug]
    required_prerequisites = MODEL_REQUIRED_PREREQUISITES[model_slug]
    required_outcome = MODEL_REQUIRED_OUTCOMES[model_slug]
    status = "blocked_pending_prerequisites"
    blocking_requirements = "empirical_readiness_audit_not_evaluated"
    if root is not None:
        audit = build_empirical_readiness_audit(root)
        blocked_prerequisites = _model_prerequisite_blockers(
            root=root,
            audit=audit,
            required_prerequisites=required_prerequisites,
            required_outcome=required_outcome,
        )
        if extra_requirements:
            extra_rows = audit.loc[audit["requirement"].isin(extra_requirements)]
            blocked_extras = extra_rows.loc[~extra_rows["status"].eq("satisfied")]
            missing_extras = sorted(
                set(extra_requirements).difference(set(extra_rows["requirement"]))
            )
        else:
            blocked_extras = pd.DataFrame()
            missing_extras = []
        if blocked_prerequisites.empty and blocked_extras.empty and not missing_extras:
            status = "ready"
            blocking_requirements = ""
        else:
            blocking_requirements = ";".join(
                [
                    *[
                        f"{row['prerequisite']}={row['blocking_reason']}"
                        for row in blocked_prerequisites.to_dict(orient="records")
                    ],
                    *[
                        f"{row['requirement']}={row['blocking_reason']}"
                        for row in blocked_extras.to_dict(orient="records")
                    ],
                    *[
                        f"{requirement}=missing_from_empirical_readiness_audit"
                        for requirement in missing_extras
                    ],
                ]
            )
    return {
        "model_slug": model_slug,
        "model_family": model_family,
        "unit_of_observation": unit_of_observation,
        "dependent_variable": dependent_variable,
        "status": status,
        "required_prerequisites": ";".join(required_prerequisites),
        "required_outcome": required_outcome,
        "model_specific_audit_requirements": ";".join(extra_requirements),
        "blocking_requirements": blocking_requirements,
        "identification_risk": identification_risk,
    }


def _model_prerequisite_blockers(
    *,
    root: Path,
    audit: pd.DataFrame,
    required_prerequisites: tuple[str, ...],
    required_outcome: str,
) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for prerequisite in required_prerequisites:
        if prerequisite == "simultaneity_and_common_shock_strategy":
            satisfied, reason = _identification_strategy_review_status(root)
            if not satisfied:
                records.append(
                    {
                        "prerequisite": prerequisite,
                        "status": "not_satisfied",
                        "blocking_reason": reason,
                    }
                )
            continue
        requirements = _model_prerequisite_audit_requirements(
            prerequisite,
            required_outcome=required_outcome,
        )
        rows = audit.loc[audit["requirement"].isin(requirements)]
        blocked = rows.loc[~rows["status"].eq("satisfied")]
        missing = sorted(set(requirements).difference(set(rows["requirement"])))
        if not blocked.empty or missing:
            reason = ";".join(
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
            records.append(
                {
                    "prerequisite": prerequisite,
                    "status": "not_satisfied",
                    "blocking_reason": reason or _blocking_reason(prerequisite),
                }
            )
    return pd.DataFrame.from_records(
        records,
        columns=["prerequisite", "status", "blocking_reason"],
    )


def _model_prerequisite_audit_requirements(
    prerequisite: str,
    *,
    required_outcome: str,
) -> tuple[str, ...]:
    requirements = PREREQUISITE_AUDIT_REQUIREMENTS[prerequisite]
    if prerequisite != "sufficient_observations_and_variation":
        return requirements
    if required_outcome == "sectoral_export_growth":
        return tuple(
            "sectoral_export_growth_coverage"
            if requirement == "dependent_variable_coverage"
            else requirement
            for requirement in requirements
        )
    return requirements


def empty_design_matrix() -> pd.DataFrame:
    """Return a schema-stable empty design matrix."""

    return pd.DataFrame(
        columns=[
            "sector_code",
            "year",
            "outcome_variable",
            "dependent_variable_value",
            "dependent_variable_source_file",
            "dependent_variable_source_column",
            "colonial_exposure",
            "european_exposure",
            "controls_available",
            "source_id",
            "source_quality",
        ]
    )


def empty_sectoral_output_panel() -> pd.DataFrame:
    """Return a schema-stable sectoral output panel placeholder."""

    return pd.DataFrame(
        columns=[
            "sector_code",
            "year",
            "source_classification",
            "source_sector_code",
            "harmonised_sector_code",
            "classification_version",
            "mapping_version",
            "nominal_output",
            "real_output",
            "output_growth",
            "deflator",
            "unit",
            "currency",
            "price_basis",
            "deflator_base",
            "classification_break_status",
            "real_output_method",
            "growth_method",
            "lag_definition",
            "log_or_percent_change",
            "base_year",
            "source_id",
            "source_quality",
        ]
    )


def empty_sectoral_output_source_registry() -> pd.DataFrame:
    """Return a schema-stable sectoral-output source registry placeholder."""

    return pd.DataFrame(columns=SECTORAL_OUTPUT_SOURCE_REGISTRY_COLUMNS)


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
        available = _available_non_null_year_flow_pairs(
            frame,
            flow_code="X",
            value_columns=[
                "world_exports_pte",
                "exports_pte",
                "trade_value_pte",
                "trade_value",
            ],
            root=root,
        ) + _available_non_null_year_flow_pairs(
            frame,
            flow_code="M",
            value_columns=[
                "world_imports_pte",
                "imports_pte",
                "trade_value_pte",
                "trade_value",
            ],
            root=root,
        )
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


def _sectoral_output_source_registry(root: Path) -> dict[str, object]:
    registry = _sectoral_output_source_registry_frame(root)
    if registry.empty:
        return _record(
            "sectoral_output_source_registry",
            1,
            0,
            "sectoral output source registry is missing or empty",
        )
    reviewed = _reviewed_source_registry(registry)
    return _record(
        "sectoral_output_source_registry",
        1,
        int(not reviewed.empty),
        "no reviewed sectoral-output source is registered",
    )


def _sectoral_output_source_coverage(root: Path) -> dict[str, object]:
    panel = _sectoral_output_panel(root)
    required = _sectoral_output_grid_requirement(panel, root=root)
    if panel.empty:
        return _record(
            "sectoral_output_source_coverage",
            required,
            0,
            "sectoral output panel is missing or empty",
        )
    available = _non_null_sector_year_observations(
        _reviewed_output_panel(root, panel),
        ["nominal_output"],
    )
    return _record(
        "sectoral_output_source_coverage",
        required,
        available,
        "reviewed nominal sector-year output observations do not cover the configured sample",
    )


def _real_output_coverage(root: Path) -> dict[str, object]:
    panel = _sectoral_output_panel(root)
    required = _sectoral_output_grid_requirement(panel, root=root)
    if panel.empty:
        return _record(
            "real_output_coverage",
            required,
            0,
            "sectoral output panel is missing or empty",
        )
    available = _non_null_sector_year_observations(
        _reviewed_output_panel(root, panel),
        ["real_output"],
    )
    return _record(
        "real_output_coverage",
        required,
        available,
        "reviewed real sector-year output observations do not cover the configured sample",
    )


def _output_growth_coverage(root: Path) -> dict[str, object]:
    panel = _sectoral_output_panel(root)
    required = _sectoral_output_grid_requirement(
        panel,
        root=root,
        sample_years=_growth_sample_years(root),
    )
    if panel.empty:
        return _record(
            "output_growth_coverage",
            required,
            0,
            "sectoral output panel is missing or empty",
        )
    reviewed = _reviewed_output_panel(root, panel)
    reviewed = reviewed.loc[reviewed["year"].isin(_growth_sample_years(root))]
    available = _non_null_sector_year_observations(reviewed, ["output_growth"])
    return _record(
        "output_growth_coverage",
        required,
        available,
        "reviewed sector-year output-growth observations do not cover the configured sample",
    )


def _deflator_coverage(root: Path) -> dict[str, object]:
    panel = _sectoral_output_panel(root)
    required = _sectoral_output_grid_requirement(panel, root=root)
    if panel.empty:
        return _record(
            "price_deflator_coverage",
            required,
            0,
            "sectoral output panel is missing or empty",
        )
    available = _non_null_sector_year_observations(
        _reviewed_output_panel(root, panel),
        ["deflator"],
    )
    return _record(
        "price_deflator_coverage",
        required,
        available,
        "sector-year price deflator observations do not cover the configured sample",
    )


def _outcome_source_provenance(root: Path) -> dict[str, object]:
    panel = _sectoral_output_panel(root)
    growth_years = _growth_sample_years(root)
    required = _sectoral_output_grid_requirement(panel, root=root, sample_years=growth_years)
    if panel.empty:
        return _record(
            "outcome_source_provenance",
            required,
            0,
            "sectoral output panel is missing or empty",
        )
    reviewed = _reviewed_output_panel(root, panel)
    values = pd.to_numeric(reviewed.get("output_growth", pd.Series(dtype=object)), errors="coerce")
    observed = reviewed.loc[values.notna()].copy()
    if observed.empty:
        available = 0
    else:
        complete_metadata = _complete_output_metadata_mask(observed)
        retained = observed.loc[complete_metadata & observed["year"].isin(growth_years)]
        available = int(retained[["sector_code", "year"]].drop_duplicates().shape[0])
    return _record(
        "outcome_source_provenance",
        required,
        available,
        "reviewed output-growth rows lack source identifiers or classification metadata",
    )


def _outcome_definition_consistency(root: Path) -> dict[str, object]:
    design = _complete_design_matrix(root)
    sample_years = _growth_sample_years(root)
    expected = len(sample_years) * max(MIN_USABLE_INDUSTRIES, _design_sector_count(design))
    required = ceil(expected * MIN_SECTOR_YEAR_GRID_COVERAGE)
    if design.empty:
        return _record(
            "outcome_definition_consistency",
            required,
            0,
            "empirical design matrix is not linked to reviewed sectoral output growth",
        )
    available = _non_null_sector_year_observations(design, ["dependent_variable_value"])
    return _record(
        "outcome_definition_consistency",
        required,
        available,
        "dependent-variable values do not match reviewed sectoral output growth",
    )


def _sectoral_export_growth_coverage(root: Path) -> dict[str, object]:
    panel = _industry_trade_panel(root)
    required_panel = panel.rename(columns={"target_industry_code": "sector_code"})
    required = _sectoral_output_grid_requirement(
        required_panel,
        root=root,
        sample_years=_growth_sample_years(root),
    )
    if panel.empty:
        return _record(
            "sectoral_export_growth_coverage",
            required,
            0,
            "industry trade panel is empty",
        )
    if not {"flow_code", "target_industry_code", "trade_value_usd"}.issubset(panel.columns):
        return _record(
            "sectoral_export_growth_coverage",
            required,
            0,
            "industry trade panel lacks export-value columns",
        )
    exports = panel.loc[panel["flow_code"].astype(str).eq("X")].copy()
    exports["sector_code"] = exports["target_industry_code"].astype("string").fillna("").str.strip()
    export_growth = _derived_export_growth_panel(exports)
    export_growth = export_growth.loc[export_growth["year"].isin(_growth_sample_years(root))]
    available = _non_null_sector_year_observations(export_growth, ["sectoral_export_growth"])
    return _record(
        "sectoral_export_growth_coverage",
        required,
        available,
        "sector-year export values do not cover the configured sample",
    )


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
    panel = _industry_trade_panel(root)
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
    panel = _industry_trade_panel(root)
    required_years = set(_trade_sample_years(root))
    if panel.empty:
        return _record("usable_years", len(required_years), 0, "industry trade panel is empty")
    available_years = set(pd.to_numeric(panel["year"], errors="coerce").dropna().astype(int))
    available = len(required_years & available_years)
    return _record(
        "usable_years",
        len(required_years),
        available,
        "industry trade panel does not cover every configured sample year",
    )


def _usable_growth_years(root: Path) -> dict[str, object]:
    panel = _industry_trade_panel(root)
    required_years = set(_growth_sample_years(root))
    if panel.empty:
        return _record(
            "usable_growth_years",
            len(required_years),
            0,
            "industry trade panel is empty",
        )
    available_years = set(pd.to_numeric(panel["year"], errors="coerce").dropna().astype(int))
    available = len(required_years & available_years)
    return _record(
        "usable_growth_years",
        len(required_years),
        available,
        "industry trade panel does not cover every configured growth-sample year",
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


def _dependent_variable_coverage(root: Path) -> dict[str, object]:
    design = _complete_design_matrix(root)
    sample_years = _growth_sample_years(root)
    expected = len(sample_years) * max(MIN_USABLE_INDUSTRIES, _design_sector_count(design))
    required = ceil(expected * MIN_SECTOR_YEAR_GRID_COVERAGE)
    if design.empty:
        return _record(
            "dependent_variable_coverage",
            required,
            0,
            "empirical design matrix is empty or lacks numeric dependent-variable values",
        )
    available = _non_null_sector_year_observations(design, ["dependent_variable_value"])
    return _record(
        "dependent_variable_coverage",
        required,
        available,
        "numeric dependent-variable values do not cover the configured sector-year sample",
    )


def _identification_variables(root: Path) -> dict[str, object]:
    design = _complete_base_design_matrix(root)
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
    design = _complete_base_design_matrix(root)
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
    design = _complete_base_design_matrix(root)
    required = len(_growth_sample_years(root))
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
    design = _complete_base_design_matrix(root)
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
    design = _complete_base_design_matrix(root)
    if design.empty:
        return _record(
            "observation_parameter_ratio",
            1,
            0,
            "empirical design matrix is empty or lacks sector/year exposure controls",
        )
    observations = len(design)
    estimated_parameters = _fixed_effect_parameter_count(design)
    required = estimated_parameters + 1
    return _record(
        "observation_parameter_ratio",
        required,
        observations,
        "observations do not exceed exposure and fixed-effect parameter count",
    )


def _sector_year_uniqueness(root: Path) -> dict[str, object]:
    design = _complete_base_design_matrix(root)
    if design.empty:
        return _record(
            "sector_year_uniqueness",
            1,
            0,
            "empirical design matrix is empty or lacks sector/year exposure controls",
        )
    duplicate_count = int(design.duplicated(subset=["sector_code", "year"], keep=False).sum())
    return _record(
        "sector_year_uniqueness",
        1,
        int(duplicate_count == 0),
        "empirical design matrix contains duplicate sector-year observations",
    )


def _sector_year_grid_coverage(root: Path) -> dict[str, object]:
    design = _complete_base_design_matrix(root)
    sample_years = _growth_sample_years(root)
    expected = len(sample_years) * max(MIN_USABLE_INDUSTRIES, _design_sector_count(design))
    required = ceil(expected * MIN_SECTOR_YEAR_GRID_COVERAGE)
    if design.empty:
        return _record(
            "sector_year_grid_coverage",
            required,
            0,
            "empirical design matrix is empty or lacks sector/year exposure controls",
        )
    observed = int(design[["sector_code", "year"]].drop_duplicates().shape[0])
    return _record(
        "sector_year_grid_coverage",
        required,
        observed,
        f"sector-year grid coverage is below {MIN_SECTOR_YEAR_GRID_COVERAGE:.0%}",
    )


def _minimum_sector_years_per_industry(root: Path) -> dict[str, object]:
    design = _complete_base_design_matrix(root)
    if design.empty:
        return _record(
            "minimum_sector_years_per_industry",
            MIN_YEARS_PER_SECTOR,
            0,
            "empirical design matrix is empty or lacks sector/year exposure controls",
        )
    years_per_sector = design.groupby("sector_code")["year"].nunique()
    available = int(years_per_sector.min()) if not years_per_sector.empty else 0
    return _record(
        "minimum_sector_years_per_industry",
        MIN_YEARS_PER_SECTOR,
        available,
        f"at least one retained sector has fewer than {MIN_YEARS_PER_SECTOR} sample years",
    )


def _residual_degrees_of_freedom(root: Path) -> dict[str, object]:
    design = _complete_base_design_matrix(root)
    if design.empty:
        return _record(
            "residual_degrees_of_freedom",
            MIN_RESIDUAL_DEGREES_OF_FREEDOM,
            0,
            "empirical design matrix is empty or lacks sector/year exposure controls",
        )
    residual_df = max(len(design) - _fixed_effect_parameter_count(design), 0)
    return _record(
        "residual_degrees_of_freedom",
        MIN_RESIDUAL_DEGREES_OF_FREEDOM,
        residual_df,
        f"fewer than {MIN_RESIDUAL_DEGREES_OF_FREEDOM} residual degrees of freedom are available",
    )


def _independent_cluster_count(root: Path) -> dict[str, object]:
    design = _complete_base_design_matrix(root)
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


def _complete_base_design_matrix(root: Path) -> pd.DataFrame:
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
    complete = complete.loc[complete["year"].isin(set(_growth_sample_years(root)))].copy()
    complete["year"] = complete["year"].astype(int)
    return complete


def _complete_design_matrix(root: Path) -> pd.DataFrame:
    design = _read_csv(root / "data/interim/live/empirical_design_matrix.csv")
    required_columns = {
        "sector_code",
        "year",
        "outcome_variable",
        "dependent_variable_value",
        "dependent_variable_source_file",
        "dependent_variable_source_column",
        "colonial_exposure",
        "european_exposure",
        "controls_available",
        "source_id",
        "source_quality",
    }
    if design.empty or not required_columns.issubset(design.columns):
        return pd.DataFrame()
    complete = design.copy()
    complete["year"] = pd.to_numeric(complete["year"], errors="coerce")
    complete["dependent_variable_value"] = pd.to_numeric(
        complete["dependent_variable_value"], errors="coerce"
    )
    complete["colonial_exposure"] = pd.to_numeric(complete["colonial_exposure"], errors="coerce")
    complete["european_exposure"] = pd.to_numeric(complete["european_exposure"], errors="coerce")
    complete["sector_code"] = complete["sector_code"].astype("string").fillna("").str.strip()
    for column in [
        "outcome_variable",
        "dependent_variable_source_file",
        "dependent_variable_source_column",
        "source_id",
        "source_quality",
    ]:
        complete[column] = complete[column].astype("string").fillna("").str.strip()
    complete = complete.loc[
        complete["sector_code"].ne("")
        & complete["year"].notna()
        & complete["dependent_variable_value"].notna()
        & complete["colonial_exposure"].notna()
        & complete["european_exposure"].notna()
        & complete["outcome_variable"].eq(DEPENDENT_VARIABLE_NAME)
        & complete["dependent_variable_source_file"].eq(DEPENDENT_VARIABLE_SOURCE_FILE)
        & complete["dependent_variable_source_column"].eq(DEPENDENT_VARIABLE_SOURCE_COLUMN)
        & complete["source_id"].ne("")
        & complete["source_quality"].str.lower().isin(REVIEWED_SOURCE_QUALITIES)
    ].copy()
    complete = complete.loc[complete["year"].isin(set(_growth_sample_years(root)))].copy()
    complete["year"] = complete["year"].astype(int)
    outcome = _reviewed_output_growth_panel(root)
    if outcome.empty:
        return pd.DataFrame()
    merged = complete.merge(
        outcome,
        on=["sector_code", "year", "source_id"],
        how="inner",
        validate="many_to_one",
    )
    if merged.empty:
        return pd.DataFrame()
    consistent = np.isclose(
        merged["dependent_variable_value"].astype(float),
        merged[DEPENDENT_VARIABLE_SOURCE_COLUMN].astype(float),
        rtol=1e-9,
        atol=1e-12,
        equal_nan=False,
    )
    return merged.loc[consistent, complete.columns].copy()


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


def _fixed_effect_parameter_count(design: pd.DataFrame) -> int:
    if design.empty:
        return 0
    exposure = design[["colonial_exposure", "european_exposure"]].astype(float).to_numpy()
    sectors = pd.get_dummies(design["sector_code"].astype(str), drop_first=False, dtype=float)
    years = pd.get_dummies(design["year"].astype(int).astype(str), drop_first=False, dtype=float)
    model = np.column_stack([sectors.to_numpy(dtype=float), years.to_numpy(dtype=float), exposure])
    return int(np.linalg.matrix_rank(model))


def _design_sector_count(design: pd.DataFrame) -> int:
    if design.empty or "sector_code" not in design:
        return 0
    return int(design["sector_code"].nunique())


def _available_year_flow_pairs(frame: pd.DataFrame, *, root: Path) -> int:
    pairs = frame.loc[
        frame["year"].isin(_trade_sample_years(root))
        & frame["flow_code"].astype(str).isin(TRADE_SAMPLE_FLOWS),
        ["year", "flow_code"],
    ]
    return int(pairs.drop_duplicates().shape[0])


def _available_non_null_year_flow_pairs(
    frame: pd.DataFrame,
    *,
    flow_code: str,
    value_columns: list[str],
    root: Path,
) -> int:
    available_columns = [column for column in value_columns if column in frame.columns]
    if not available_columns:
        return 0
    sample = frame.loc[
        frame["year"].isin(_trade_sample_years(root))
        & frame["flow_code"].astype(str).eq(flow_code),
        ["year", "flow_code", *available_columns],
    ].copy()
    if sample.empty:
        return 0
    values = sample[available_columns].apply(pd.to_numeric, errors="coerce")
    observed = sample.loc[values.notna().any(axis=1), ["year", "flow_code"]]
    return int(observed.drop_duplicates().shape[0])


def _sectoral_output_panel(root: Path) -> pd.DataFrame:
    panel = _read_csv(root / "data/processed/live/sectoral_output_panel.csv")
    if panel.empty or not {"sector_code", "year"}.issubset(panel.columns):
        return pd.DataFrame()
    sample = panel.copy()
    sample["year"] = pd.to_numeric(sample["year"], errors="coerce")
    sample["sector_code"] = sample["sector_code"].astype("string").fillna("").str.strip()
    sample = sample.loc[
        sample["sector_code"].ne("") & sample["year"].isin(set(_trade_sample_years(root)))
    ].copy()
    sample["year"] = sample["year"].astype(int)
    return sample


def _sectoral_output_source_registry_frame(root: Path) -> pd.DataFrame:
    registry = _read_csv(root / "data/raw/live/sectoral_output/source_registry.csv")
    if registry.empty or not set(SECTORAL_OUTPUT_SOURCE_REGISTRY_COLUMNS).issubset(
        registry.columns
    ):
        return pd.DataFrame(columns=SECTORAL_OUTPUT_SOURCE_REGISTRY_COLUMNS)
    output = registry.copy()
    output["source_id"] = output["source_id"].astype("string").fillna("").str.strip()
    output["review_status"] = output["review_status"].astype("string").fillna("").str.strip()
    return output.loc[output["source_id"].ne("")].copy()


def _reviewed_source_registry(registry: pd.DataFrame) -> pd.DataFrame:
    if registry.empty:
        return pd.DataFrame(columns=SECTORAL_OUTPUT_SOURCE_REGISTRY_COLUMNS)
    reviewed = registry.copy()
    reviewed["review_status"] = reviewed["review_status"].astype(str).str.strip().str.lower()
    return reviewed.loc[reviewed["review_status"].isin(REVIEWED_SOURCE_QUALITIES)].copy()


def _reviewed_output_panel(root: Path, panel: pd.DataFrame) -> pd.DataFrame:
    if panel.empty or not {"source_id", "source_quality"}.issubset(panel.columns):
        return pd.DataFrame(columns=panel.columns)
    registry = _reviewed_source_registry(_sectoral_output_source_registry_frame(root))
    if registry.empty:
        return pd.DataFrame(columns=panel.columns)
    reviewed_sources = set(registry["source_id"].astype("string").fillna("").str.strip())
    reviewed = panel.copy()
    reviewed["source_id"] = reviewed["source_id"].astype("string").fillna("").str.strip()
    reviewed["source_quality"] = (
        reviewed["source_quality"].astype("string").fillna("").str.strip().str.lower()
    )
    return reviewed.loc[
        reviewed["source_id"].ne("")
        & reviewed["source_id"].isin(reviewed_sources)
        & reviewed["source_quality"].isin(REVIEWED_SOURCE_QUALITIES)
    ].copy()


def _reviewed_output_growth_panel(root: Path) -> pd.DataFrame:
    panel = _reviewed_output_panel(root, _sectoral_output_panel(root))
    required_columns = {"sector_code", "year", "source_id", DEPENDENT_VARIABLE_SOURCE_COLUMN}
    if panel.empty or not required_columns.issubset(panel.columns):
        return pd.DataFrame()
    values = pd.to_numeric(panel[DEPENDENT_VARIABLE_SOURCE_COLUMN], errors="coerce")
    derived = _derived_output_growth(panel)
    metadata_mask = _complete_output_metadata_mask(panel)
    output_columns = ["sector_code", "year", "source_id", DEPENDENT_VARIABLE_SOURCE_COLUMN]
    growth_consistent = (
        values.notna()
        & derived.notna()
        & np.isclose(
            values.astype(float),
            derived.astype(float),
            rtol=1e-9,
            atol=1e-12,
            equal_nan=False,
        )
    )
    output = panel.loc[
        growth_consistent & metadata_mask & panel["year"].isin(_growth_sample_years(root)),
        output_columns,
    ].copy()
    output[DEPENDENT_VARIABLE_SOURCE_COLUMN] = pd.to_numeric(
        output[DEPENDENT_VARIABLE_SOURCE_COLUMN], errors="coerce"
    )
    return output.drop_duplicates(subset=["sector_code", "year", "source_id"])


def _complete_output_metadata_mask(panel: pd.DataFrame) -> pd.Series:
    if panel.empty:
        return pd.Series(dtype=bool)
    missing_columns = [column for column in REQUIRED_OUTPUT_METADATA_COLUMNS if column not in panel]
    if missing_columns:
        return pd.Series(False, index=panel.index)
    mask = pd.Series(True, index=panel.index)
    for column in REQUIRED_OUTPUT_METADATA_COLUMNS:
        values = panel[column].astype("string").fillna("").str.strip()
        mask &= values.ne("") & ~values.str.lower().isin(PLACEHOLDER_METADATA_VALUES)
    mask &= (
        panel["classification_break_status"]
        .astype("string")
        .fillna("")
        .str.strip()
        .str.lower()
        .isin(RESOLVED_CLASSIFICATION_BREAK_STATUSES)
    )
    mask &= panel["growth_method"].astype("string").fillna("").str.strip().eq(OUTPUT_GROWTH_METHOD)
    mask &= (
        panel["lag_definition"]
        .astype("string")
        .fillna("")
        .str.strip()
        .eq(OUTPUT_GROWTH_LAG_DEFINITION)
    )
    mask &= (
        panel["log_or_percent_change"]
        .astype("string")
        .fillna("")
        .str.strip()
        .eq(OUTPUT_GROWTH_METHOD)
    )
    mask &= (
        panel["harmonised_sector_code"]
        .astype("string")
        .fillna("")
        .str.strip()
        .eq(panel["sector_code"].astype("string").fillna("").str.strip())
    )
    return mask


def _derived_output_growth(panel: pd.DataFrame) -> pd.Series:
    if panel.empty or not {"sector_code", "year", "real_output"}.issubset(panel.columns):
        return pd.Series(np.nan, index=panel.index, dtype="float64")
    working = panel[["sector_code", "year", "real_output"]].copy()
    working["real_output"] = pd.to_numeric(working["real_output"], errors="coerce")
    working = working.sort_values(["sector_code", "year"])
    previous = working.groupby("sector_code", dropna=False)["real_output"].shift(1)
    previous_year = working.groupby("sector_code", dropna=False)["year"].shift(1)
    valid = (
        working["real_output"].gt(0)
        & previous.gt(0)
        & previous_year.notna()
        & working["year"].sub(previous_year).eq(1)
    )
    derived = pd.Series(np.nan, index=working.index, dtype="float64")
    derived.loc[valid] = np.log(working.loc[valid, "real_output"]) - np.log(previous.loc[valid])
    return derived.reindex(panel.index)


def _derived_export_growth_panel(exports: pd.DataFrame) -> pd.DataFrame:
    if exports.empty or not {"sector_code", "year", "trade_value_usd"}.issubset(exports.columns):
        return pd.DataFrame(columns=["sector_code", "year", "sectoral_export_growth"])
    grouped = exports.copy()
    grouped["trade_value_usd"] = pd.to_numeric(grouped["trade_value_usd"], errors="coerce")
    grouped = (
        grouped.groupby(["sector_code", "year"], as_index=False, dropna=False).agg(
            trade_value_usd=("trade_value_usd", "sum")
        )
    ).sort_values(["sector_code", "year"])
    previous = grouped.groupby("sector_code", dropna=False)["trade_value_usd"].shift(1)
    previous_year = grouped.groupby("sector_code", dropna=False)["year"].shift(1)
    valid = (
        grouped["trade_value_usd"].gt(0)
        & previous.gt(0)
        & previous_year.notna()
        & grouped["year"].sub(previous_year).eq(1)
    )
    grouped["sectoral_export_growth"] = np.nan
    grouped.loc[valid, "sectoral_export_growth"] = np.log(
        grouped.loc[valid, "trade_value_usd"]
    ) - np.log(previous.loc[valid])
    return grouped[["sector_code", "year", "sectoral_export_growth"]]


def _sectoral_output_grid_requirement(
    panel: pd.DataFrame,
    *,
    root: Path,
    sample_years: tuple[int, ...] | None = None,
) -> int:
    years = sample_years or _trade_sample_years(root)
    sector_count = (
        int(panel["sector_code"].nunique())
        if not panel.empty and "sector_code" in panel.columns
        else 0
    )
    expected = len(years) * max(MIN_USABLE_INDUSTRIES, sector_count)
    return ceil(expected * MIN_SECTOR_YEAR_GRID_COVERAGE)


def _non_null_sector_year_observations(frame: pd.DataFrame, value_columns: list[str]) -> int:
    available_columns = [column for column in value_columns if column in frame.columns]
    if frame.empty or not available_columns:
        return 0
    values = frame[available_columns].apply(pd.to_numeric, errors="coerce")
    observed = frame.loc[values.notna().any(axis=1), ["sector_code", "year"]]
    return int(observed.drop_duplicates().shape[0])


def _industry_trade_panel(root: Path) -> pd.DataFrame:
    panel = _read_csv(root / "data/processed/live/industry_trade_panel.csv")
    if panel.empty or "year" not in panel.columns:
        return pd.DataFrame()
    sample = panel.copy()
    sample["year"] = pd.to_numeric(sample["year"], errors="coerce")
    sample = sample.loc[sample["year"].isin(set(_trade_sample_years(root)))].copy()
    sample["year"] = sample["year"].astype(int)
    return sample


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


def _growth_sample_years(root: Path) -> tuple[int, ...]:
    sample_years = _trade_sample_years(root)
    return sample_years[1:] if len(sample_years) > 1 else ()


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
