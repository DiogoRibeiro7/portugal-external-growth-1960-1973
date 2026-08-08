"""BPstat macro and broad-sector series normalisation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

NORMALISED_COLUMNS = [
    "source",
    "series_id",
    "slug",
    "concept",
    "label",
    "year",
    "reference_date",
    "value",
    "units",
    "frequency",
    "price_basis",
    "domain_id",
    "dataset_id",
    "territorial_definition",
    "reconstruction_method",
    "methodological_breaks",
    "source_status",
    "review_status",
    "use_status",
    "raw_file",
]

MACRO_COLUMN_MAP = {
    "gdp_current_prices_annual": "nominal_gdp_million_eur",
    "real_gdp_chain_linked_annual": "real_gdp_chain_linked_million_eur",
    "gdp_growth_chain_volume_yoy_annual": "real_gdp_yoy_percent",
    "gdp_deflator_annual": "gdp_deflator_index",
    "gdp_deflator_yoy_annual": "gdp_deflator_yoy_percent",
    "exports_goods_services_current_annual": "exports_goods_services_million_eur",
    "imports_goods_services_current_annual": "imports_goods_services_million_eur",
    "exports_goods_services_chain_linked_annual": "real_exports_goods_services_million_eur",
    "imports_goods_services_chain_linked_annual": "real_imports_goods_services_million_eur",
    "gross_fixed_capital_formation_current_annual": "gfcf_million_eur",
    "gross_fixed_capital_formation_chain_linked_annual": "real_gfcf_million_eur",
    "resident_population_total": "resident_population_thousand_people",
}

BROAD_SECTOR_COLUMN_MAP = {
    "manufacturing_gva_current_annual": "manufacturing_gva_million_eur",
    "manufacturing_gva_chain_linked_annual": "real_manufacturing_gva_million_eur",
    "manufacturing_gva_deflator_yoy_annual": "manufacturing_gva_deflator_yoy_percent",
}

PROCESSED_START_YEAR = 1950
PROCESSED_END_YEAR = 1973

PRIORITY_VARIABLES = {
    "real GDP": "real_gdp_chain_linked_annual",
    "nominal GDP": "gdp_current_prices_annual",
    "GDP deflator": "gdp_deflator_annual",
    "gross fixed capital formation": "gross_fixed_capital_formation_current_annual",
    "exports and imports": "exports_goods_services_current_annual",
    "population": "resident_population_total",
    "gross value added by broad sector": "manufacturing_gva_current_annual",
    "industrial/manufacturing output": "manufacturing_gva_chain_linked_annual",
}


def build_bpstat_macro_outputs(
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, str]:
    """Create normalised and processed BPstat macro outputs from local raw snapshots."""

    registry = _read_csv(root / "data/interim/live/bpstat_series_registry.csv")
    raw_files = sorted((root / "data/raw/live/bpstat").glob("series_*.csv"))
    normalised = normalise_bpstat_raw(raw_files, registry, root=root)
    macro = build_processed_macro_dataset(normalised)
    broad_sector = build_processed_broad_sector_dataset(normalised, macro)
    dictionary = build_bpstat_data_dictionary(registry, normalised)
    validation = build_bpstat_macro_validation_report(normalised, registry)
    notes = build_bpstat_macro_cross_checks(normalised, macro, broad_sector, validation)
    return normalised, macro, broad_sector, dictionary, validation, notes


def normalise_bpstat_raw(
    raw_files: list[Path], registry: pd.DataFrame, *, root: Path
) -> pd.DataFrame:
    """Normalise single-series BPstat raw CSV snapshots to a source-specific long table."""

    if not raw_files or registry.empty:
        return pd.DataFrame(columns=NORMALISED_COLUMNS)
    records: list[dict[str, object]] = []
    registry_by_id = {int(row["series_id"]): row for row in registry.to_dict(orient="records")}
    for path in raw_files:
        series_id = _series_id_from_metadata(path)
        if series_id is None or series_id not in registry_by_id:
            continue
        meta = registry_by_id[series_id]
        frame = pd.read_csv(path)
        if "reference_date" not in frame or "value" not in frame:
            continue
        for row in frame.to_dict(orient="records"):
            reference_date = str(row["reference_date"])
            year = pd.to_datetime(reference_date, errors="coerce").year
            records.append(
                {
                    "source": "BPstat Data API v1",
                    "series_id": series_id,
                    "slug": meta["slug"],
                    "concept": meta["concept"],
                    "label": meta["label"],
                    "year": int(year) if pd.notna(year) else pd.NA,
                    "reference_date": reference_date,
                    "value": pd.to_numeric(pd.Series([row.get("value")]), errors="coerce").iloc[0],
                    "units": meta["units"],
                    "frequency": meta["frequency"],
                    "price_basis": meta["price_basis"],
                    "domain_id": meta["domain_id"],
                    "dataset_id": meta["dataset_id"],
                    "territorial_definition": meta["territorial_definition"],
                    "reconstruction_method": meta["reconstruction_method"],
                    "methodological_breaks": meta["methodological_breaks"],
                    "source_status": meta["source_status"],
                    "review_status": meta["review_status"],
                    "use_status": _use_status(str(meta["review_status"])),
                    "raw_file": path.relative_to(root).as_posix(),
                }
            )
    return pd.DataFrame.from_records(records, columns=NORMALISED_COLUMNS).sort_values(
        ["slug", "year"]
    )


def build_processed_macro_dataset(normalised: pd.DataFrame) -> pd.DataFrame:
    """Build a wide macro context table without splicing inconsistent series."""

    macro = _pivot_slugs(normalised, MACRO_COLUMN_MAP)
    if macro.empty:
        return macro
    if {
        "real_gdp_chain_linked_million_eur",
        "resident_population_thousand_people",
    }.issubset(macro.columns):
        macro["real_gdp_per_resident_thousand_eur"] = (
            macro["real_gdp_chain_linked_million_eur"]
            / macro["resident_population_thousand_people"]
        )
    macro["source_status"] = "bpstat_context_with_methodological_caveats"
    macro["coverage_status"] = _coverage_status(macro)
    return macro


def build_processed_broad_sector_dataset(
    normalised: pd.DataFrame, macro: pd.DataFrame
) -> pd.DataFrame:
    """Build broad-sector context table for manufacturing GVA."""

    sector = _pivot_slugs(normalised, BROAD_SECTOR_COLUMN_MAP)
    if sector.empty:
        return sector
    if "year" in macro:
        denominator_columns = [
            "year",
            "nominal_gdp_million_eur",
            "real_gdp_chain_linked_million_eur",
        ]
        available = [column for column in denominator_columns if column in macro]
        sector = sector.merge(macro[available], on="year", how="left")
    if {"manufacturing_gva_million_eur", "nominal_gdp_million_eur"}.issubset(sector.columns):
        sector["manufacturing_gva_share_of_nominal_gdp"] = (
            sector["manufacturing_gva_million_eur"] / sector["nominal_gdp_million_eur"]
        )
    if {
        "real_manufacturing_gva_million_eur",
        "real_gdp_chain_linked_million_eur",
    }.issubset(sector.columns):
        sector["real_manufacturing_gva_share_of_real_gdp"] = (
            sector["real_manufacturing_gva_million_eur"]
            / sector["real_gdp_chain_linked_million_eur"]
        )
    sector["sector"] = "manufacturing"
    sector["source_status"] = "bpstat_broad_sector_context_with_classification_caveats"
    sector["coverage_status"] = _coverage_status(sector)
    ordered = [
        "year",
        "sector",
        *[column for column in sector.columns if column not in {"year", "sector"}],
    ]
    return sector[ordered]


def build_bpstat_data_dictionary(registry: pd.DataFrame, normalised: pd.DataFrame) -> pd.DataFrame:
    """Create a data dictionary for extracted BPstat series."""

    if registry.empty:
        return pd.DataFrame()
    extracted = set(normalised["series_id"].dropna().astype(int)) if not normalised.empty else set()
    rows = []
    for row in registry.to_dict(orient="records"):
        rows.append(
            {
                "series_id": row["series_id"],
                "slug": row["slug"],
                "concept": row["concept"],
                "label": row["label"],
                "units": row["units"],
                "frequency": row["frequency"],
                "price_basis": row["price_basis"],
                "domain_id": row["domain_id"],
                "dataset_id": row["dataset_id"],
                "territorial_definition": row["territorial_definition"],
                "methodological_breaks": row["methodological_breaks"],
                "source_status": row["source_status"],
                "review_status": row["review_status"],
                "extraction_status": (
                    "extracted" if int(row["series_id"]) in extracted else "not_extracted"
                ),
                "analytical_use": _use_status(str(row["review_status"])),
            }
        )
    return pd.DataFrame.from_records(rows).sort_values(["concept", "slug"])


def build_bpstat_macro_validation_report(
    normalised: pd.DataFrame, registry: pd.DataFrame
) -> pd.DataFrame:
    """Report coverage and review caveats for BPstat macro outputs."""

    rows: list[dict[str, object]] = []
    if registry.empty:
        return pd.DataFrame(columns=["check", "severity", "message"])
    for row in registry.to_dict(orient="records"):
        slug = str(row["slug"])
        series = normalised.loc[normalised["slug"].eq(slug)] if not normalised.empty else normalised
        years = pd.to_numeric(series.get("year", pd.Series(dtype="float64")), errors="coerce")
        project = series.loc[years.between(1960, 1973)] if not series.empty else series
        rows.append(
            {
                "check": f"series.{slug}.coverage",
                "severity": "warning" if project.empty else "info",
                "message": (
                    f"{slug}: {len(project)} non-null project-period rows; "
                    f"review_status={row['review_status']}; "
                    f"methodological_breaks={row['methodological_breaks']}"
                ),
                "first_year": int(years.min()) if not years.dropna().empty else pd.NA,
                "last_year": int(years.max()) if not years.dropna().empty else pd.NA,
                "project_period_non_null_rows": int(project["value"].notna().sum())
                if not project.empty and "value" in project
                else 0,
            }
        )
    extracted_slugs = set(normalised["slug"]) if not normalised.empty else set()
    for variable, slug in PRIORITY_VARIABLES.items():
        rows.append(
            {
                "check": f"priority.{variable}",
                "severity": "info" if slug in extracted_slugs else "warning",
                "message": (
                    f"{variable}: {'available' if slug in extracted_slugs else 'not available'} "
                    f"from BPstat candidate {slug}."
                ),
                "first_year": pd.NA,
                "last_year": pd.NA,
                "project_period_non_null_rows": pd.NA,
            }
        )
    for missing in (
        "employment",
        "balance-of-payments components",
        "remittances",
        "tourism receipts",
    ):
        rows.append(
            {
                "check": f"priority.{missing}",
                "severity": "warning",
                "message": f"{missing}: no BPstat series with 1960-1973 coverage is extracted.",
                "first_year": pd.NA,
                "last_year": pd.NA,
                "project_period_non_null_rows": 0,
            }
        )
    return pd.DataFrame.from_records(rows)


def build_bpstat_macro_cross_checks(
    normalised: pd.DataFrame,
    macro: pd.DataFrame,
    broad_sector: pd.DataFrame,
    validation: pd.DataFrame,
) -> str:
    """Write human-readable BPstat macro cross-check notes."""

    project_rows = (
        normalised.loc[pd.to_numeric(normalised["year"], errors="coerce").between(1960, 1973)]
        if not normalised.empty
        else normalised
    )
    warnings = (
        validation.loc[validation["severity"].eq("warning")]
        if not validation.empty
        else pd.DataFrame()
    )
    extracted_count = normalised["slug"].nunique() if not normalised.empty else 0
    return "\n".join(
        [
            "BPstat macro and broad-sector cross-checks",
            "==========================================",
            "",
            f"Extracted BPstat series: {extracted_count}",
            f"Project-period long rows: {len(project_rows)}",
            f"Processed macro years: {len(macro) if not macro.empty else 0}",
            f"Processed broad-sector years: {len(broad_sector) if not broad_sector.empty else 0}",
            f"Validation warnings: {len(warnings)}",
            "",
            "Series are source-preserving BPstat context series. They are not spliced",
            "with INE/Comtrade merchandise-trade aggregates and retain methodological",
            "and territorial-definition caveats from the reviewed registry.",
            "",
        ]
    )


def _pivot_slugs(normalised: pd.DataFrame, column_map: dict[str, str]) -> pd.DataFrame:
    if normalised.empty:
        return pd.DataFrame()
    subset = normalised.loc[normalised["slug"].isin(column_map)]
    if subset.empty:
        return pd.DataFrame()
    pivot = subset.pivot_table(index="year", columns="slug", values="value", aggfunc="first")
    pivot = pivot.rename(columns=column_map).reset_index()
    pivot.columns.name = None
    pivot = pivot.loc[
        pd.to_numeric(pivot["year"], errors="coerce").between(
            PROCESSED_START_YEAR, PROCESSED_END_YEAR
        )
    ]
    return pivot.sort_values("year").reset_index(drop=True)


def _coverage_status(frame: pd.DataFrame) -> str:
    years = set(pd.to_numeric(frame["year"], errors="coerce").dropna().astype(int))
    required = set(range(1960, 1974))
    if required.issubset(years):
        return "covers_1960_1973"
    if years.intersection(required):
        return "partial_1960_1973"
    return "outside_1960_1973"


def _series_id_from_metadata(csv_path: Path) -> int | None:
    metadata_path = csv_path.with_suffix(".json.metadata.json")
    if not metadata_path.exists():
        metadata_path = csv_path.with_suffix(".metadata.json")
    if not metadata_path.exists():
        raw_metadata = csv_path.with_suffix(".json").with_suffix(".metadata.json")
        metadata_path = raw_metadata
    if not metadata_path.exists():
        metadata_path = csv_path.parent / f"{csv_path.stem}.json.metadata.json"
    if not metadata_path.exists():
        return None
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    series_ids = payload.get("series_ids")
    if not isinstance(series_ids, list) or len(series_ids) != 1:
        return None
    return int(series_ids[0])


def _use_status(review_status: str) -> str:
    if review_status.startswith("accepted_for_context"):
        return "context_only_not_empirical_identification"
    if review_status.startswith("rejected"):
        return "not_usable_for_project_period"
    return "held_for_review"


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)
