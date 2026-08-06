from __future__ import annotations

from pathlib import Path

import pandas as pd
from pytest import MonkeyPatch
from typer.testing import CliRunner

from portugal_external_growth.cli import app


def test_validate_command_exits_nonzero_on_integrity_error(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    _write_bootstrap_gdp(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    (config / "manual_sources.yml").write_text("manual_sources: []\n", encoding="utf-8")
    monkeypatch.setenv("PEG_ROOT", str(tmp_path))

    result = CliRunner().invoke(app, ["validate"])

    assert result.exit_code == 1
    assert (tmp_path / "results/validation/data_integrity_report.csv").exists()
    assert (tmp_path / "results/validation/research_readiness_report.csv").exists()


def test_validate_command_exits_zero_on_integrity_pass(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    _write_bootstrap_gdp(tmp_path)
    _write_valid_preliminary_trade(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    (config / "manual_sources.yml").write_text("manual_sources: []\n", encoding="utf-8")
    monkeypatch.setenv("PEG_ROOT", str(tmp_path))

    result = CliRunner().invoke(app, ["validate"])

    assert result.exit_code == 0


def _write_bootstrap_gdp(root: Path) -> None:
    data_dir = root / "data/raw/bootstrap"
    data_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "country_code": "PRT",
                "indicator_code": "NY.GDP.MKTP.KD.ZG",
                "year": 1961,
                "value": 6.0,
            }
        ]
    ).to_csv(data_dir / "world_bank_gdp_growth_portugal_1961_1973.csv", index=False)


def _write_valid_preliminary_trade(root: Path) -> None:
    results = root / "results/live"
    results.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "classification_scheme": "fixture",
                "partner_group": "colonies",
                "trade_value_usd": 20.0,
                "world_value_usd": 100.0,
                "world_share": 0.2,
                "value_method": "selected_partner_sum",
            },
            {
                "year": 1962,
                "flow_code": "X",
                "classification_scheme": "fixture",
                "partner_group": "true_rest_of_world",
                "trade_value_usd": 80.0,
                "world_value_usd": 100.0,
                "world_share": 0.8,
                "value_method": "world_total_minus_selected_groups",
            },
        ]
    ).to_csv(results / "preliminary_trade_group_shares.csv", index=False)
