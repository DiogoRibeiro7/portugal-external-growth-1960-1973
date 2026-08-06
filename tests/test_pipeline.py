from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.pipeline import build, validate
from portugal_external_growth.settings import Settings


def test_build_generates_trade_orientation_from_local_comtrade(tmp_path: Path) -> None:
    _write_bootstrap_gdp(tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    (config / "partner_groups.yml").write_text(
        """
groups:
  colonies:
    members:
      - {code: 24, name: Angola, start_year: 1960, end_year: 1973}
""",
        encoding="utf-8",
    )
    raw_dir = tmp_path / "data/raw/live/comtrade"
    raw_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "period": 1962,
                "reporterCode": 620,
                "partnerCode": 24,
                "partnerDesc": "Angola",
                "flowCode": "X",
                "cmdCode": "TOTAL",
                "primaryValue": 25.0,
            },
            {
                "period": 1962,
                "reporterCode": 620,
                "partnerCode": 826,
                "partnerDesc": "United Kingdom",
                "flowCode": "X",
                "cmdCode": "TOTAL",
                "primaryValue": 75.0,
            },
        ]
    ).to_csv(raw_dir / "trade.csv", index=False)

    build(Settings(root=tmp_path))

    result = pd.read_csv(tmp_path / "results/live/trade_orientation_by_group.csv")
    assert result["flow_share"].sum() == 1.0
    assert result.loc[result["partner_group"] == "colonies", "trade_value_usd"].iloc[0] == 25.0


def test_validate_writes_integrity_and_readiness_reports(tmp_path: Path) -> None:
    _write_bootstrap_gdp(tmp_path)
    _write_valid_preliminary_trade(tmp_path)
    config = tmp_path / "config"
    config.mkdir(exist_ok=True)
    (config / "manual_sources.yml").write_text("manual_sources: []\n", encoding="utf-8")

    passed = validate(Settings(root=tmp_path))

    integrity = pd.read_csv(tmp_path / "results/validation/data_integrity_report.csv")
    readiness = pd.read_csv(tmp_path / "results/validation/research_readiness_report.csv")
    assert passed
    assert integrity.loc[0, "check"] == "data_integrity.status"
    assert "not_ready" in readiness["severity"].tolist()


def _write_bootstrap_gdp(root: Path) -> None:
    path = root / "data/raw/bootstrap"
    path.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "country_name": "Portugal",
                "country_code": "PRT",
                "indicator": "GDP growth",
                "indicator_code": "NY.GDP.MKTP.KD.ZG",
                "year": 1961,
                "value": 5.0,
                "unit": "percent",
                "source": "fixture",
                "snapshot_role": "fixture",
            }
        ]
    ).to_csv(path / "world_bank_gdp_growth_portugal_1961_1973.csv", index=False)


def _write_valid_preliminary_trade(root: Path) -> None:
    path = root / "results/live"
    path.mkdir(parents=True)
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
    ).to_csv(path / "preliminary_trade_group_shares.csv", index=False)
