from __future__ import annotations

import pandas as pd

from portugal_external_growth.data_dictionary import build_analytical_data_dictionary
from portugal_external_growth.empirical import empty_design_matrix


def test_analytical_data_dictionary_preserves_empty_design_schema() -> None:
    dictionary = build_analytical_data_dictionary(
        "data/interim/live/empirical_design_matrix.csv",
        empty_design_matrix(),
    )

    assert dictionary["column_name"].tolist() == empty_design_matrix().columns.tolist()
    assert set(dictionary["dataset_path"]) == {"data/interim/live/empirical_design_matrix.csv"}
    assert "intentionally empty" in dictionary["analytical_use"].iloc[0]
    assert (
        dictionary.loc[dictionary["column_name"].eq("controls_available"), "unit"].iloc[0]
        == "boolean"
    )


def test_analytical_data_dictionary_uses_dataset_specific_release_caveat() -> None:
    frame = pd.DataFrame(columns=["year", "trade_value_usd", "estimate_status"])

    dictionary = build_analytical_data_dictionary(
        "data/processed/live/industry_trade_panel.csv",
        frame,
    )

    assert "product-level trade" in dictionary["source_status"].iloc[0]
    assert dictionary.loc[dictionary["column_name"].eq("trade_value_usd"), "unit"].iloc[0] == "USD"


def test_context_and_exposure_dictionaries_use_specific_column_metadata() -> None:
    macro = pd.DataFrame(columns=["year", "nominal_gdp_million_eur", "coverage_status"])
    exposure = pd.DataFrame(columns=["total_exports_usd", "colonial_exports_usd"])

    macro_dictionary = build_analytical_data_dictionary(
        "data/processed/live/portugal_macro_context.csv",
        macro,
    )
    exposure_dictionary = build_analytical_data_dictionary(
        "data/processed/live/industry_exposure_panel.csv",
        exposure,
    )

    assert (
        macro_dictionary.loc[
            macro_dictionary["column_name"].eq("nominal_gdp_million_eur"), "unit"
        ].iloc[0]
        == "million EUR"
    )
    assert (
        exposure_dictionary.loc[
            exposure_dictionary["column_name"].eq("total_exports_usd"), "unit"
        ].iloc[0]
        == "USD"
    )
    assert not exposure_dictionary["description"].str.contains(" column in ").any()
