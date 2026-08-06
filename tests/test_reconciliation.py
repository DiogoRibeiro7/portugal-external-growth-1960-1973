from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.reconciliation import (
    build_trade_reconciliation_notes,
    build_trade_source_comparison,
    finalise_trade_reconciliation,
)


def test_reconciliation_keeps_conflicting_source_values() -> None:
    comparison = pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "source": "UN Comtrade",
                "source_value": 100.0,
                "benchmark_source": "UN Comtrade",
            },
            {
                "year": 1962,
                "flow_code": "X",
                "source": "INE",
                "source_value": 90.0,
                "benchmark_source": "UN Comtrade",
            },
        ]
    )

    result = finalise_trade_reconciliation(comparison)

    assert result.loc[result["source"] == "INE", "source_value"].iloc[0] == 90.0
    assert result.loc[result["source"] == "INE", "difference_from_benchmark"].iloc[0] == -10.0


def test_trade_source_comparison_adds_missing_independent_sources(tmp_path: Path) -> None:
    audit_dir = tmp_path / "results/diagnostics/comtrade_coverage"
    audit_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "world_value_usd": 100.0,
                "territorial_definition_status": "requires_review",
            }
        ]
    ).to_csv(audit_dir / "comtrade_coverage_audit.csv", index=False)

    comparison = build_trade_source_comparison(tmp_path)

    assert set(comparison["source"]) == {"UN Comtrade", "INE", "OECD", "EFTA", "CEPII TRADHIST"}
    assert (
        comparison.loc[comparison["source"] == "UN Comtrade", "confidence_status"].iloc[0]
        == "usable_with_territorial_caveat"
    )
    assert set(comparison.loc[comparison["source"] != "UN Comtrade", "confidence_status"]) == {
        "missing_source"
    }


def test_trade_reconciliation_notes_list_missing_sources() -> None:
    comparison = pd.DataFrame(
        [
            {"source": "UN Comtrade", "confidence_status": "usable_with_territorial_caveat"},
            {"source": "INE", "confidence_status": "missing_source"},
            {"source": "CEPII TRADHIST", "confidence_status": "missing_source"},
        ]
    )

    notes = build_trade_reconciliation_notes(comparison)

    assert "CEPII TRADHIST" in notes
    assert "INE" in notes
