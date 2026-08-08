from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from portugal_external_growth.macro import build_bpstat_macro_outputs
from portugal_external_growth.pipeline import build_bpstat_macro
from portugal_external_growth.settings import Settings


def test_bpstat_macro_outputs_preserve_source_series_and_build_context_tables(
    tmp_path: Path,
) -> None:
    _write_registry(tmp_path)
    _write_raw_series(tmp_path, 1, "1960-12-31", 100.0)
    _write_raw_series(tmp_path, 2, "1960-12-31", 50.0)
    _write_raw_series(tmp_path, 3, "1960-12-31", 10.0)
    _write_raw_series(tmp_path, 4, "1960-12-31", 250.0)

    normalised, macro, broad_sector, dictionary, validation, notes = build_bpstat_macro_outputs(
        tmp_path
    )

    assert set(normalised["series_id"]) == {1, 2, 3, 4}
    assert macro.loc[0, "nominal_gdp_million_eur"] == 100.0
    assert macro.loc[0, "real_gdp_per_resident_thousand_eur"] == 5.0
    assert broad_sector.loc[0, "manufacturing_gva_share_of_nominal_gdp"] == 0.1
    assert set(dictionary["extraction_status"]) == {"extracted"}
    assert "employment" in " ".join(validation["message"].astype(str))
    assert "Series are source-preserving BPstat context series" in notes


def test_pipeline_writes_bpstat_macro_outputs(tmp_path: Path) -> None:
    _write_registry(tmp_path)
    _write_raw_series(tmp_path, 1, "1960-12-31", 100.0)
    _write_raw_series(tmp_path, 2, "1960-12-31", 50.0)
    _write_raw_series(tmp_path, 3, "1960-12-31", 10.0)
    _write_raw_series(tmp_path, 4, "1960-12-31", 250.0)

    build_bpstat_macro(Settings(root=tmp_path))

    assert (tmp_path / "data/interim/live/bpstat_macro_long.csv").exists()
    assert (tmp_path / "data/processed/live/portugal_macro_context.csv").exists()
    assert (tmp_path / "data/processed/live/portugal_broad_sector_context.csv").exists()
    assert (tmp_path / "results/validation/bpstat_macro_validation_report.csv").exists()


def _write_registry(root: Path) -> None:
    output = root / "data/interim/live"
    output.mkdir(parents=True)
    rows = [
        _registry_row(1, "gdp_current_prices_annual", "nominal_gdp"),
        _registry_row(2, "resident_population_total", "population"),
        _registry_row(3, "manufacturing_gva_current_annual", "manufacturing_value_added"),
        _registry_row(4, "real_gdp_chain_linked_annual", "real_gdp"),
    ]
    pd.DataFrame(rows).to_csv(output / "bpstat_series_registry.csv", index=False)


def _registry_row(series_id: int, slug: str, concept: str) -> dict[str, object]:
    return {
        "series_id": series_id,
        "slug": slug,
        "concept": concept,
        "label": slug,
        "domain_id": 1,
        "dataset_id": "dataset",
        "frequency": "annual",
        "units": "millions of euros" if series_id != 2 else "thousands of people",
        "price_basis": "current_prices",
        "territorial_definition": "Portugal",
        "reconstruction_method": "source",
        "methodological_breaks": "not_reviewed",
        "source_status": "source",
        "review_status": "accepted_for_context_not_enabled_for_extraction",
    }


def _write_raw_series(root: Path, series_id: int, reference_date: str, value: float) -> None:
    output = root / "data/raw/live/bpstat"
    output.mkdir(parents=True, exist_ok=True)
    stem = f"series_{series_id}"
    pd.DataFrame([{"reference_date": reference_date, "value": value}]).to_csv(
        output / f"{stem}.csv",
        index=False,
    )
    (output / f"{stem}.json.metadata.json").write_text(
        json.dumps({"series_ids": [series_id]}),
        encoding="utf-8",
    )
