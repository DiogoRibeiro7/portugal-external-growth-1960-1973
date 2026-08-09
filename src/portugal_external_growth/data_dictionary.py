"""Schema dictionaries for analytical datasets."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

DATA_DICTIONARY_COLUMNS = [
    "dataset_path",
    "column_name",
    "data_type",
    "unit",
    "description",
    "source_status",
    "analytical_use",
]


@dataclass(frozen=True)
class DatasetDictionarySpec:
    """Dataset-level dictionary defaults."""

    source_status: str
    analytical_use: str


DATASET_SPECS = {
    "data/processed/live/validated_annual_aggregate_external_orientation.csv": (
        DatasetDictionarySpec(
            source_status=(
                "mixed source-backed benchmark rows and explicitly blocked non-benchmark years"
            ),
            analytical_use="descriptive aggregate-orientation table; not a causal design matrix",
        )
    ),
    "data/processed/live/industry_trade_panel.csv": DatasetDictionarySpec(
        source_status="blocked until product-level trade and industry mappings are validated",
        analytical_use="not enabled for empirical analysis while empty or incompletely mapped",
    ),
    "data/processed/live/industry_exposure_panel.csv": DatasetDictionarySpec(
        source_status="blocked until industry trade panel is populated from validated mappings",
        analytical_use="descriptive exposure panel only after mapping prerequisites are satisfied",
    ),
    "data/interim/live/empirical_design_matrix.csv": DatasetDictionarySpec(
        source_status="schema placeholder pending empirical prerequisites",
        analytical_use="no model fitting; intentionally empty until readiness audit passes",
    ),
    "data/interim/live/efta_policy_dataset.csv": DatasetDictionarySpec(
        source_status="blocked until EFTA sources, tariff rows, and mappings are acquired",
        analytical_use="no tariff exposure estimates are inferred from placeholder rows",
    ),
}

COLUMN_DESCRIPTIONS = {
    "year": ("calendar year", "year"),
    "flow_code": ("trade flow code, usually X for exports or M for imports", "code"),
    "source_classification": ("source product classification revision", "code"),
    "mapping_scope": ("scope of the product-to-industry mapping", "category"),
    "mapping_version": ("registered mapping version identifier", "identifier"),
    "target_industry_code": ("target industry code assigned by the mapping", "code"),
    "target_industry_group": ("target industry group assigned by the mapping", "category"),
    "target_industry_label": ("human-readable target industry label", "label"),
    "partner_group": ("configured partner grouping used in the aggregation", "category"),
    "trade_value_usd": ("trade value in current US dollars", "USD"),
    "product_count": ("number of product codes contributing to the row", "count"),
    "mapping_weight": ("mapping weight applied to product trade values", "share"),
    "coverage_count": ("observed coverage count for the row", "count"),
    "expected_count": ("expected coverage count for the row", "count"),
    "coverage_ratio": ("observed coverage divided by expected coverage", "share"),
    "estimate_status": ("machine-readable status describing whether values are observed", "status"),
    "source_quality": ("machine-readable source-quality note", "status"),
    "world_exports_pte": ("total merchandise exports from the preferred aggregate source", "PTE"),
    "world_imports_pte": ("total merchandise imports from the preferred aggregate source", "PTE"),
    "colonial_exports_complete_pte": (
        "complete colonial-market exports from source-backed aggregate rows",
        "PTE",
    ),
    "colonial_imports_complete_pte": (
        "complete colonial-market imports from source-backed aggregate rows",
        "PTE",
    ),
    "colonial_exports_observed_comtrade_usd": (
        "observed Comtrade colonial-partner export subtotal retained as a diagnostic",
        "USD",
    ),
    "colonial_imports_observed_comtrade_usd": (
        "observed Comtrade colonial-partner import subtotal retained as a diagnostic",
        "USD",
    ),
    "complete_colonial_export_share": (
        "complete colonial exports divided by total exports",
        "share",
    ),
    "complete_colonial_import_share": (
        "complete colonial imports divided by total imports",
        "share",
    ),
    "observed_colonial_export_share": (
        "observed Comtrade colonial export subtotal divided by Comtrade world exports",
        "share",
    ),
    "observed_colonial_import_share": (
        "observed Comtrade colonial import subtotal divided by Comtrade world imports",
        "share",
    ),
    "efta_participation_exports_pte": (
        "exports to the contemporaneous EFTA aggregate printed in the INE source",
        "PTE",
    ),
    "efta_participation_imports_pte": (
        "imports from the contemporaneous EFTA aggregate printed in the INE source",
        "PTE",
    ),
    "eec_membership_exports_pte": (
        "exports to the contemporaneous EEC/CEE aggregate printed in the INE source",
        "PTE",
    ),
    "eec_membership_imports_pte": (
        "imports from the contemporaneous EEC/CEE aggregate printed in the INE source",
        "PTE",
    ),
    "fixed_europe_exports_pte": (
        "exports to the configured fixed European partner sample when explicit "
        "source-backed rows exist",
        "PTE",
    ),
    "fixed_europe_imports_pte": (
        "imports from the configured fixed European partner sample when explicit "
        "source-backed rows exist",
        "PTE",
    ),
    "efta_export_share": (
        "contemporaneous EFTA exports divided by total exports",
        "share",
    ),
    "eec_export_share": (
        "contemporaneous EEC/CEE exports divided by total exports",
        "share",
    ),
    "fixed_europe_export_share": (
        "fixed European partner-sample exports divided by total exports when the fixed "
        "sample is observed",
        "share",
    ),
    "non_colonial_world_exports_pte": (
        "total exports minus complete colonial-market exports; this residual still includes Europe",
        "PTE",
    ),
    "non_colonial_world_imports_pte": (
        "total imports minus complete colonial-market imports; this residual still includes Europe",
        "PTE",
    ),
    "unassigned_residual_exports_pte": (
        "exports not assigned after the explicitly documented aggregate components are reconciled",
        "PTE",
    ),
    "unassigned_residual_imports_pte": (
        "imports not assigned after the explicitly documented aggregate components are reconciled",
        "PTE",
    ),
    "colonial_observed_partner_count": (
        "number of colonial partner areas observed in the Comtrade diagnostic subtotal",
        "count",
    ),
    "colonial_expected_partner_count": (
        "expected colonial partner-area count for the Comtrade diagnostic subtotal",
        "count",
    ),
    "source_status": ("machine-readable source availability and review status", "status"),
    "reconciliation_status": ("cross-source reconciliation status", "status"),
    "source_currency": ("currency of source-backed aggregate monetary values", "currency"),
    "valuation_basis": ("source-specific trade valuation convention", "description"),
    "territorial_definition": ("territorial scope documented for the row", "description"),
    "notes": ("free-text caveat or source note", "text"),
    "sector_code": ("sector identifier for empirical-design rows", "code"),
    "outcome_variable": ("registered dependent variable placeholder", "variable"),
    "colonial_exposure": ("colonial-demand exposure variable", "share"),
    "european_exposure": ("European-demand exposure variable", "share"),
    "controls_available": ("whether required control variables are available", "boolean"),
    "commodity_code": ("source commodity or product code", "code"),
    "commodity_description": ("source commodity or product description", "label"),
    "product_group": ("policy product group", "category"),
    "tariff_before": ("tariff rate or duty measure before policy change", "source unit"),
    "tariff_after": ("tariff rate or duty measure after policy change", "source unit"),
    "scheduled_reduction": ("scheduled tariff reduction", "source unit"),
    "actual_reduction": ("observed tariff reduction", "source unit"),
    "exception_status": ("whether the product is covered by exceptions", "status"),
    "portuguese_special_treatment_status": (
        "status of Portugal-specific EFTA treatment",
        "status",
    ),
    "quota_restriction_status": ("status of quota or quantitative restrictions", "status"),
    "source_id": ("registered source identifier", "identifier"),
    "page": ("source page reference", "reference"),
    "table": ("source table reference", "reference"),
}


def build_analytical_data_dictionary(dataset_path: str, frame: pd.DataFrame) -> pd.DataFrame:
    """Create a deterministic data dictionary for an analytical dataset."""

    spec = DATASET_SPECS.get(
        dataset_path,
        DatasetDictionarySpec(
            source_status="not specified",
            analytical_use="not specified",
        ),
    )
    records: list[dict[str, object]] = []
    for column in frame.columns:
        description, unit = COLUMN_DESCRIPTIONS.get(
            str(column),
            (f"{column} column in {dataset_path}", "not_applicable"),
        )
        records.append(
            {
                "dataset_path": dataset_path,
                "column_name": column,
                "data_type": str(frame[column].dtype),
                "unit": unit,
                "description": description,
                "source_status": spec.source_status,
                "analytical_use": spec.analytical_use,
            }
        )
    return pd.DataFrame.from_records(records, columns=DATA_DICTIONARY_COLUMNS)
