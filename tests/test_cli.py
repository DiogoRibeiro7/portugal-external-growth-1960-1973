from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from pytest import MonkeyPatch
from typer.testing import CliRunner

import portugal_external_growth.cli as cli
from portugal_external_growth.cli import app


class DummySettings:
    def __init__(self, root: Path) -> None:
        self._root = root

    def resolved_root(self) -> Path:
        return self._root


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


@pytest.mark.parametrize(
    ("command", "target_name", "expects_root", "args"),
    [
        ("bootstrap", "bootstrap", True, []),
        ("init-manual-templates", "init_manual_templates", True, []),
        ("extract-world-bank", "extract_world_bank", False, ["--overwrite"]),
        ("extract-comtrade", "extract_comtrade", False, ["--overwrite"]),
        ("extract-comtrade-products", "extract_comtrade_products", False, ["--overwrite"]),
        ("audit-comtrade-coverage", "audit_comtrade_coverage", False, ["--overwrite"]),
        ("extract-bpstat", "extract_bpstat", False, ["--overwrite"]),
        ("review-bpstat-registry", "review_bpstat_registry", False, []),
        ("prepare-ine-transcription", "prepare_ine_transcription", False, []),
        ("init-ine-transcription", "init_ine_transcription_inputs", False, []),
        ("compare-ine-transcriptions", "compare_ine_transcription_passes", False, []),
        ("build-ine-harmonised", "build_ine_harmonised_outputs", False, []),
        ("reconcile-trade-sources", "reconcile_trade_sources", False, []),
        ("build-sitc-industry-mapping", "build_sitc_industry_mapping", False, []),
        ("build-product-industry-mapping", "build_product_industry_mapping", False, []),
        ("build-descriptive-results", "build_descriptive_results", False, []),
        ("build-bpstat-macro", "build_bpstat_macro", False, []),
        (
            "design-product-comtrade-extraction",
            "design_product_comtrade_extraction",
            False,
            [],
        ),
        (
            "build-validated-aggregate-orientation",
            "build_validated_aggregate_orientation",
            False,
            [],
        ),
        ("prepare-empirical-extension", "prepare_empirical_extension", False, []),
        ("build", "build", False, []),
        ("refresh-sources", "refresh_sources", False, ["--overwrite"]),
        ("run-diagnostics", "run_diagnostics", False, []),
    ],
)
def test_cli_dispatches_pipeline_commands(
    command: str,
    target_name: str,
    expects_root: bool,
    args: list[str],
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[tuple[str, Any, dict[str, Any]]] = []
    monkeypatch.setattr(cli, "_settings", lambda: DummySettings(tmp_path))

    def fake_target(first_arg: Any, **kwargs: Any) -> None:
        calls.append((target_name, first_arg, kwargs))

    monkeypatch.setattr(cli, target_name, fake_target)

    result = CliRunner().invoke(app, [command, *args])

    assert result.exit_code == 0
    assert calls
    assert calls[0][0] == target_name
    if expects_root:
        assert calls[0][1] == tmp_path
    else:
        assert isinstance(calls[0][1], DummySettings)
    if "--overwrite" in args:
        assert calls[0][2] == {"overwrite": True}


@pytest.mark.parametrize(
    ("command", "target_name"),
    [
        ("reproduce-from-local", "reproduce_from_local"),
        ("run-all-available", "run_all_available"),
        ("run-all", "run_all"),
    ],
)
def test_cli_exits_nonzero_when_boolean_workflow_fails(
    command: str,
    target_name: str,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "_settings", lambda: DummySettings(tmp_path))
    monkeypatch.setattr(cli, target_name, lambda *args, **kwargs: False)

    result = CliRunner().invoke(app, [command])

    assert result.exit_code == 1


@pytest.mark.parametrize(
    ("command", "target_name", "args"),
    [
        ("reproduce-from-local", "reproduce_from_local", []),
        ("run-all-available", "run_all_available", ["--overwrite"]),
        ("run-all", "run_all", ["--overwrite"]),
    ],
)
def test_cli_exits_zero_when_boolean_workflow_passes(
    command: str,
    target_name: str,
    args: list[str],
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(cli, "_settings", lambda: DummySettings(tmp_path))

    def fake_target(*_args: Any, **kwargs: Any) -> bool:
        calls.append(kwargs)
        return True

    monkeypatch.setattr(cli, target_name, fake_target)

    result = CliRunner().invoke(app, [command, *args])

    assert result.exit_code == 0
    if "--overwrite" in args:
        assert calls == [{"overwrite": True}]


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
