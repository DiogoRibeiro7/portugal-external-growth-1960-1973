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
    data_dir = tmp_path / "data/raw/bootstrap"
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
    config = tmp_path / "config"
    config.mkdir()
    (config / "manual_sources.yml").write_text("manual_sources: []\n", encoding="utf-8")
    monkeypatch.setenv("PEG_ROOT", str(tmp_path))

    result = CliRunner().invoke(app, ["validate"])

    assert result.exit_code == 1
    assert (tmp_path / "results/validation/data_integrity_report.csv").exists()
    assert (tmp_path / "results/validation/research_readiness_report.csv").exists()
