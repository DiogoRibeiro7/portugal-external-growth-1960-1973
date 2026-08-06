"""Empirical-design preparation without causal claims."""

from __future__ import annotations

import pandas as pd

PREREQUISITES = [
    "reviewed_bilateral_trade_panel",
    "stable_product_classification",
    "portuguese_sectoral_output_data",
    "documented_product_to_industry_mapping",
    "sufficient_observations_and_variation",
    "simultaneity_and_common_shock_strategy",
]


def build_empirical_prerequisite_status() -> pd.DataFrame:
    """Return the current empirical-design prerequisite status."""

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


def build_model_specification_registry() -> pd.DataFrame:
    """Create a registry of candidate model families without fitting them."""

    return pd.DataFrame(
        [
            {
                "model_slug": "shift_share_external_demand",
                "model_family": "shift_share_exposure",
                "unit_of_observation": "sector_year",
                "dependent_variable": "sectoral_output_growth",
                "status": "blocked_pending_prerequisites",
                "identification_risk": "Requires stable sector-output panel and exposure shares.",
            },
            {
                "model_slug": "sector_year_fixed_effects",
                "model_family": "fixed_effects_panel",
                "unit_of_observation": "sector_year",
                "dependent_variable": "sectoral_output_growth",
                "status": "blocked_pending_prerequisites",
                "identification_risk": "Common European growth shocks require explicit controls.",
            },
            {
                "model_slug": "efta_tariff_exposure",
                "model_family": "tariff_exposure_design",
                "unit_of_observation": "sector_year",
                "dependent_variable": "sectoral_export_or_output_growth",
                "status": "blocked_pending_prerequisites",
                "identification_risk": "Requires documented EFTA tariff schedules.",
            },
            {
                "model_slug": "colonial_demand_shifters",
                "model_family": "external_demand_shift_design",
                "unit_of_observation": "sector_year",
                "dependent_variable": "sectoral_export_or_output_growth",
                "status": "blocked_pending_prerequisites",
                "identification_risk": "Commodity price channels must be controlled directly.",
            },
        ]
    )


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
