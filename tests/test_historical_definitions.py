from __future__ import annotations

from pathlib import Path

import pandas as pd


def test_historical_colonial_crosswalk_distinguishes_ine_and_harmonised_groups() -> None:
    root = Path(__file__).resolve().parents[1]
    crosswalk = pd.read_csv(root / "data/interim/live/historical_colonial_partner_crosswalk.csv")

    assert set(crosswalk["source_category_entity_count"]) == {8}
    assert set(crosswalk["harmonised_group_entity_count"]) == {7}
    assert int(crosswalk["in_harmonised_colonial_market"].sum()) == 7

    india = crosswalk.loc[crosswalk["entity_id"].eq("portuguese_india")].iloc[0]
    assert india["ine_group"] == "Ultramar Portugues"
    assert not bool(india["in_harmonised_colonial_market"])
    assert india["definition_scope"] == "ine_1962_ultramar_source_category_only"


def test_territorial_definition_review_records_colonial_definition_distinction() -> None:
    root = Path(__file__).resolve().parents[1]
    review = pd.read_csv(
        root / "results/diagnostics/territorial_definitions/portugal_1962_1973.csv"
    )

    assert "ine_ultramar_portugues_1962" in set(review["source_key"])
    assert "harmonised_colonial_market_group" in set(review["source_key"])

    harmonised = review.loc[review["source_key"].eq("harmonised_colonial_market_group")].iloc[0]
    assert harmonised["status"] == "analytical_definition_documented"
    assert "Portuguese India" in harmonised["methodological_note"]
