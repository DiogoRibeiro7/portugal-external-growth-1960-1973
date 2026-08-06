from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.validation import (
    build_file_manifest,
    validate_preliminary_trade_shares,
    validate_trade_shares,
    validate_unique,
)


def test_validate_unique_reports_duplicates() -> None:
    frame = pd.DataFrame({"year": [1970, 1970], "value": [1, 2]})
    issues = validate_unique(frame, ["year"], name="example")
    assert issues[0].severity == "error"


def test_validate_trade_shares_accepts_complete_groups() -> None:
    frame = pd.DataFrame(
        {
            "year": [1970, 1970],
            "flow_code": ["X", "X"],
            "flow_share": [0.25, 0.75],
        }
    )
    assert validate_trade_shares(frame) == []


def test_validate_preliminary_trade_shares_requires_world_sum() -> None:
    frame = pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "classification_scheme": "current",
                "partner_group": "colonies",
                "trade_value_usd": 20.0,
                "world_value_usd": 100.0,
                "world_share": 0.2,
                "value_method": "selected_partner_sum",
            },
            {
                "year": 1962,
                "flow_code": "X",
                "classification_scheme": "current",
                "partner_group": "true_rest_of_world",
                "trade_value_usd": 80.0,
                "world_value_usd": 100.0,
                "world_share": 0.8,
                "value_method": "world_total_minus_selected_groups",
            },
        ]
    )
    assert validate_preliminary_trade_shares(frame) == []


def test_manifest_excludes_manifest_outputs_and_uses_posix_paths(tmp_path: Path) -> None:
    data = tmp_path / "data"
    manifests = tmp_path / "results/manifests"
    data.mkdir(parents=True)
    manifests.mkdir(parents=True)
    (data / "table.csv").write_text("a\n1\n", encoding="utf-8")
    (data / "table.csv.metadata.json").write_text("{}\n", encoding="utf-8")
    (manifests / "current_manifest.csv").write_text("old\n", encoding="utf-8")

    manifest = build_file_manifest(tmp_path)

    assert "data/table.csv" in manifest["relative_path"].tolist()
    assert "data/table.csv.metadata.json" in manifest["relative_path"].tolist()
    assert not any(path.startswith("results/manifests/") for path in manifest["relative_path"])
