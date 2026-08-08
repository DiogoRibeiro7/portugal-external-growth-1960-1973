from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.efta_policy import build_efta_policy_outputs
from portugal_external_growth.empirical import build_empirical_readiness_audit


def test_efta_policy_outputs_block_when_empirical_audit_is_missing(tmp_path: Path) -> None:
    sources, policy, product_mapping, coverage, status, notes = build_efta_policy_outputs(tmp_path)

    assert sources.loc[0, "registration_status"] == "blocked"
    assert policy.empty
    assert product_mapping.empty
    assert set(coverage["status"]) == {"blocked"}
    assert status.loc[0, "status"] == "blocked"
    assert "empirical_readiness_audit_missing" in str(status.loc[0, "blocking_reason"])
    assert "No tariff rates" in notes


def test_efta_policy_outputs_preserve_readiness_blocking_reasons(tmp_path: Path) -> None:
    results = tmp_path / "results/live"
    results.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "requirement": "product_level_coverage",
                "status": "blocked",
                "blocking_reason": "product rows missing",
            },
            {
                "requirement": "usable_industries",
                "status": "blocked",
                "blocking_reason": "industry panel empty",
            },
        ]
    ).to_csv(results / "empirical_readiness_audit.csv", index=False)

    _sources, policy, _product_mapping, _coverage, status, _notes = build_efta_policy_outputs(
        tmp_path
    )

    assert policy.empty
    blocking_reason = str(status.loc[0, "blocking_reason"])
    assert "product_level_coverage=product rows missing" in blocking_reason
    assert "usable_industries=industry panel empty" in blocking_reason


def test_empirical_audit_does_not_count_blocked_efta_policy_file_as_available(
    tmp_path: Path,
) -> None:
    diagnostics = tmp_path / "results/diagnostics/efta_policy"
    diagnostics.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "status": "blocked",
                "blocking_reason": "policy rows missing",
            }
        ]
    ).to_csv(diagnostics / "efta_policy_status.csv", index=False)
    data = tmp_path / "data/interim/live"
    data.mkdir(parents=True)
    pd.DataFrame(columns=["year", "tariff_before"]).to_csv(
        data / "efta_policy_dataset.csv", index=False
    )

    audit = build_empirical_readiness_audit(tmp_path)

    row = audit.loc[audit["requirement"].eq("efta_policy_tariff_data_availability")].iloc[0]
    assert row["status"] == "blocked"
    assert row["available"] == 0
    assert "policy rows missing" in str(row["blocking_reason"])
