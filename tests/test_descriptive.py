from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.descriptive import (
    _build_export_growth_contribution,
    _build_world_denominator_groups,
    build_descriptive_trade_results,
)

MEMBERSHIPS = pd.DataFrame(
    [
        {"year": 1960, "partner_code": 24, "partner_group": "colonies"},
        {"year": 1962, "partner_code": 24, "partner_group": "colonies"},
        {"year": 1973, "partner_code": 24, "partner_group": "colonies"},
        {"year": 1960, "partner_code": 826, "partner_group": "efta"},
        {"year": 1962, "partner_code": 826, "partner_group": "efta"},
        {"year": 1960, "partner_code": 56, "partner_group": "eec"},
        {"year": 1973, "partner_code": 208, "partner_group": "eec"},
        {"year": 1973, "partner_code": 372, "partner_group": "eec"},
        {"year": 1973, "partner_code": 826, "partner_group": "eec"},
    ]
)


def test_export_growth_contribution_sums_to_one() -> None:
    group_values = pd.DataFrame(
        [
            {"year": 1962, "flow_code": "X", "partner_group": "a", "trade_value_usd": 10.0},
            {"year": 1973, "flow_code": "X", "partner_group": "a", "trade_value_usd": 15.0},
            {"year": 1962, "flow_code": "X", "partner_group": "b", "trade_value_usd": 10.0},
            {"year": 1973, "flow_code": "X", "partner_group": "b", "trade_value_usd": 20.0},
        ]
    )

    result = _build_export_growth_contribution(group_values)

    assert result["contribution_to_export_growth"].sum() == 1.0


def test_preliminary_shares_use_world_denominator_and_non_colonial_residual() -> None:
    coverage = pd.DataFrame(
        [
            {"year": 1962, "flow_code": "X", "partner_code": 0, "trade_value_usd": 100.0},
            {"year": 1962, "flow_code": "X", "partner_code": 24, "trade_value_usd": 20.0},
            {"year": 1962, "flow_code": "X", "partner_code": 826, "trade_value_usd": 30.0},
        ]
    )

    result = _build_world_denominator_groups(coverage, MEMBERSHIPS)
    current = result.loc[result["classification_scheme"] == "colonial_world_share_preliminary"]

    assert current["world_share"].sum() == 1.0
    assert current.loc[current["partner_group"] == "colonies", "world_share"].iloc[0] == 0.2
    assert (
        current.loc[current["partner_group"] == "non_colonial_world", "trade_value_usd"].iloc[0]
        == 80.0
    )


def test_preliminary_world_shares_do_not_publish_european_group_rows() -> None:
    coverage = pd.DataFrame(
        [
            {"year": 1973, "flow_code": "X", "partner_code": 0, "trade_value_usd": 100.0},
            {"year": 1973, "flow_code": "X", "partner_code": 24, "trade_value_usd": 5.0},
            {"year": 1973, "flow_code": "X", "partner_code": 208, "trade_value_usd": 10.0},
            {"year": 1973, "flow_code": "X", "partner_code": 372, "trade_value_usd": 20.0},
            {"year": 1973, "flow_code": "X", "partner_code": 826, "trade_value_usd": 30.0},
        ]
    )

    result = _build_world_denominator_groups(coverage, MEMBERSHIPS)

    assert set(result["partner_group"]) == {"colonies", "non_colonial_world"}


def test_incomplete_colonial_coverage_is_reported_as_lower_bound() -> None:
    memberships = pd.DataFrame(
        [
            {"year": 1962, "partner_code": 24, "partner_group": "colonies"},
            {"year": 1962, "partner_code": 132, "partner_group": "colonies"},
        ]
    )
    coverage = pd.DataFrame(
        [
            {"year": 1962, "flow_code": "X", "partner_code": 0, "trade_value_usd": 100.0},
            {"year": 1962, "flow_code": "X", "partner_code": 24, "trade_value_usd": 20.0},
        ]
    )

    result = _build_world_denominator_groups(coverage, memberships)
    colonies = result.loc[result["partner_group"] == "colonies"].iloc[0]

    assert colonies["trade_value_usd"] == 20.0
    assert colonies["world_share"] == 0.2
    assert pd.isna(colonies["complete_world_share"])
    assert colonies["partner_coverage_count"] == 1
    assert colonies["expected_partner_count"] == 2
    assert colonies["estimate_status"] == "incomplete_partner_lower_bound"
    residual = result.loc[result["partner_group"] == "unassigned_world_residual"].iloc[0]
    assert residual["trade_value_usd"] == 80.0
    assert pd.isna(residual["complete_group_trade_value_usd"])
    assert pd.isna(residual["complete_world_share"])
    assert residual["estimate_status"] == "residual_with_incomplete_selected_group"


def test_build_descriptive_trade_results_from_local_registry(tmp_path: Path) -> None:
    _write_partner_registry(tmp_path)
    coverage_dir = tmp_path / "data/interim/live"
    coverage_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            _coverage_row(1962, "X", "S1", 0, 100.0),
            _coverage_row(1962, "X", "S1", 24, 20.0),
            _coverage_row(1962, "X", "S1", 826, 30.0),
            _coverage_row(1973, "X", "S1", 0, 200.0),
            _coverage_row(1973, "X", "S1", 24, 40.0),
            _coverage_row(1973, "X", "S1", 208, 10.0),
            _coverage_row(1973, "X", "S1", 372, 20.0),
            _coverage_row(1973, "X", "S1", 826, 30.0),
            _coverage_row(1973, "X", "S2", 0, 999.0),
        ]
    ).to_csv(coverage_dir / "comtrade_coverage_matrix.csv", index=False)

    results = build_descriptive_trade_results(tmp_path)

    preliminary = results["preliminary_group_shares"]
    colonial = results["preliminary_colonial_share"]
    product = results["diagnostic_product_composition"]
    current_1973 = preliminary.loc[
        (preliminary["year"] == 1973)
        & (preliminary["classification_scheme"] == "colonial_world_share_preliminary")
    ]
    assert set(results) == {
        "preliminary_group_shares",
        "preliminary_colonial_share",
        "diagnostic_selected_group_values",
        "diagnostic_selected_group_shares",
        "diagnostic_period_changes",
        "diagnostic_product_composition",
        "diagnostic_concentration",
        "diagnostic_export_growth_contribution",
        "diagnostic_missingness",
    }
    assert current_1973["world_share"].sum() == 1.0
    assert set(current_1973["partner_group"]) == {"colonies", "non_colonial_world"}
    assert colonial["classification_scheme"].unique().tolist() == [
        "colonial_world_share_preliminary"
    ]
    assert "observed_colonial_share" in colonial.columns
    assert "complete_colonial_share" in colonial.columns
    assert set(product["commodity_code_source"]) == {"TOTAL"}


def test_build_descriptive_trade_results_returns_empty_tables_without_coverage(
    tmp_path: Path,
) -> None:
    results = build_descriptive_trade_results(tmp_path)

    assert all(frame.empty for frame in results.values())


def _write_partner_registry(root: Path) -> None:
    config = root / "config"
    config.mkdir()
    (config / "partner_groups.yml").write_text(
        """
groups:
  colonies:
    members:
      - {code: 24, name: Angola, start_year: 1960, end_year: 1973}
  efta:
    members:
      - {code: 826, name: United Kingdom, start_year: 1960, end_year: 1972}
  eec:
    members:
      - {code: 208, name: Denmark, start_year: 1973, end_year: 1973}
      - {code: 372, name: Ireland, start_year: 1973, end_year: 1973}
      - {code: 826, name: United Kingdom, start_year: 1973, end_year: 1973}
""",
        encoding="utf-8",
    )


def _coverage_row(
    year: int,
    flow_code: str,
    classification_code: str,
    partner_code: int,
    trade_value_usd: float,
) -> dict[str, object]:
    return {
        "year": year,
        "flow_code": flow_code,
        "classification_code": classification_code,
        "partner_code": partner_code,
        "trade_value_usd": trade_value_usd,
    }
