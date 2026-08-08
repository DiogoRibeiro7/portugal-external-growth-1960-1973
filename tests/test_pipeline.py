from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import responses

from portugal_external_growth.pipeline import (
    _apply_comtrade_snapshot_status,
    _local_comtrade_coverage_matrices,
    _snapshot_partner_codes_by_coverage_request,
    build,
    extract_comtrade_products,
    reproduce_from_local,
    run_diagnostics,
    validate,
)
from portugal_external_growth.settings import Settings


def test_build_does_not_emit_legacy_trade_orientation_with_world_row(tmp_path: Path) -> None:
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
                "partnerCode": 0,
                "partnerDesc": "World",
                "flowCode": "X",
                "cmdCode": "TOTAL",
                "primaryValue": 100.0,
            },
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

    assert not (tmp_path / "results/live/trade_orientation_by_group.csv").exists()
    assert not (tmp_path / "data/processed/live/trade_orientation_by_group.csv").exists()
    normalised = pd.read_csv(tmp_path / "data/interim/live/comtrade_normalised.csv")
    assert normalised.loc[normalised["partner_code"] == 0, "trade_value_usd"].iloc[0] == 100.0


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


def test_run_diagnostics_regenerates_local_outputs(tmp_path: Path) -> None:
    _write_local_diagnostic_inputs(tmp_path)

    run_diagnostics(Settings(root=tmp_path))

    audit = pd.read_csv(
        tmp_path / "results/diagnostics/comtrade_coverage/comtrade_coverage_audit.csv"
    )
    mapping = pd.read_csv(tmp_path / "results/live/sitc_mapping_coverage.csv")
    preliminary = pd.read_csv(tmp_path / "results/live/preliminary_trade_group_shares.csv")
    prerequisites = pd.read_csv(tmp_path / "results/live/empirical_prerequisite_status.csv")
    assert audit.loc[0, "world_value_usd"] == 100.0
    assert mapping.loc[0, "classification_revision"] == "SITC Rev.1"
    assert set(preliminary["classification_scheme"]) == {"colonial_world_share_preliminary"}
    assert set(prerequisites["status"]) == {"not_satisfied"}


def test_reproduce_from_local_runs_offline_pipeline(tmp_path: Path) -> None:
    _write_bootstrap_gdp(tmp_path)
    _write_local_diagnostic_inputs(tmp_path)

    passed = reproduce_from_local(Settings(root=tmp_path))

    assert passed
    assert (tmp_path / "results/validation/data_integrity_report.csv").exists()
    assert (tmp_path / "results/manifests/current_manifest.csv").exists()


def test_extract_comtrade_products_requires_subscription_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="COMTRADE_SUBSCRIPTION_KEY"):
        extract_comtrade_products(Settings(root=tmp_path), overwrite=True)


@responses.activate
def test_extract_comtrade_products_saves_mocked_subscription_snapshot(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.mkdir()
    (config / "comtrade.yml").write_text(
        """
comtrade:
  reporter_code: 620
  flow_codes: [X]
  years: [1962]
  classification_code: S1
  product_extraction:
    years: [1962]
    flow_codes: [X]
    reporter_code: 620
    partner_codes: [0]
    classification_code: S1
    commodity_code_batches:
      - ["0"]
    max_records: 2
    aggregate_by: partner_and_year
""",
        encoding="utf-8",
    )
    url = "https://comtradeapi.un.org/data/v1/get/C/A/S1"
    responses.add(responses.GET, url, json={"count": 1, "data": []})
    responses.add(
        responses.GET,
        url,
        json={
            "count": 1,
            "data": [
                {
                    "refYear": 1962,
                    "flowCode": "X",
                    "classificationCode": "S1",
                    "cmdCode": "0",
                    "reporterCode": 620,
                    "partnerCode": 0,
                    "primaryValue": 100.0,
                }
            ],
        },
    )

    extract_comtrade_products(
        Settings(root=tmp_path, comtrade_subscription_key="secret-key"),
        overwrite=True,
    )

    raw = tmp_path / "data/raw/live/comtrade_product/PRT_1962_X_S1_P0_0.json"
    metadata = json.loads(raw.with_suffix(".metadata.json").read_text(encoding="utf-8"))
    assert raw.exists()
    assert metadata["rows"] == 1
    assert metadata["query_parameters"]["aggregateBy"] == "partner_and_year"


def test_local_comtrade_coverage_rebuild_preserves_quality_and_snapshot_status(
    tmp_path: Path,
) -> None:
    config = tmp_path / "config"
    raw_dir = tmp_path / "data/raw/live/comtrade_availability"
    config.mkdir(parents=True)
    raw_dir.mkdir(parents=True)
    (config / "comtrade.yml").write_text("comtrade: {}\n", encoding="utf-8")
    (config / "comtrade_partner_areas.yml").write_text(
        """
comtrade_partner_areas:
  - entity_id: world
    entity_label: World
    m49_code: 0
    comtrade_area_code: 0
    comtrade_area_label: World
    start_year: 1962
    end_year: 1973
    mapping_status: comtrade_total
    mapping_source: test
  - entity_id: angola
    entity_label: Angola
    m49_code: 24
    comtrade_area_code: 24
    comtrade_area_label: Angola
    start_year: 1962
    end_year: 1973
    mapping_status: direct_area_match
    mapping_source: test
""",
        encoding="utf-8",
    )
    raw = raw_dir / "PRT_1962_X_S1_TOTAL_coverage.json"
    raw.write_text(
        json.dumps(
            {
                "data": [
                    {
                        "period": 1962,
                        "reporterCode": 620,
                        "partnerCode": 24,
                        "partnerDesc": "Angola",
                        "flowCode": "X",
                        "cmdCode": "TOTAL",
                        "primaryValue": 10.0,
                        "isReported": True,
                        "isOriginalClassification": False,
                        "legacyEstimationFlag": 1,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    raw.with_suffix(".metadata.json").write_text(
        json.dumps(
            {
                "parameters": {
                    "year": 1962,
                    "flow_code": "X",
                    "classification_code": "S1",
                    "commodity_code": "TOTAL",
                    "reporter_code": 620,
                    "partner_codes": [0, 24],
                }
            }
        ),
        encoding="utf-8",
    )

    matrices = _local_comtrade_coverage_matrices(tmp_path, (0, 24, 251))

    assert len(matrices) == 1
    row = matrices[0].iloc[0]
    assert bool(row["is_reported"])
    assert not bool(row["is_original_classification"])
    assert row["legacy_estimation_flag"] == "1"
    assert row["snapshot_status"] == "stale_against_current_configuration"
    assert row["entity_id"] == "angola"


def test_local_comtrade_coverage_rebuild_records_empty_responses(tmp_path: Path) -> None:
    raw_dir = tmp_path / "data/raw/live/comtrade_availability"
    raw_dir.mkdir(parents=True)
    raw = raw_dir / "PRT_1962_X_S2_TOTAL_coverage.json"
    raw.write_text(json.dumps({"data": []}), encoding="utf-8")
    raw.with_suffix(".metadata.json").write_text(
        json.dumps(
            {
                "parameters": {
                    "year": 1962,
                    "flow_code": "X",
                    "classification_code": "S2",
                    "commodity_code": "TOTAL",
                    "reporter_code": 620,
                    "partner_codes": [0, 24],
                }
            }
        ),
        encoding="utf-8",
    )

    matrices = _local_comtrade_coverage_matrices(tmp_path, (0, 24))

    assert matrices[0].loc[0, "raw_records"] == 0
    assert matrices[0].loc[0, "snapshot_status"] == "current_against_configuration"


def test_apply_comtrade_snapshot_status_uses_metadata_and_keeps_unmatched_rows(
    tmp_path: Path,
) -> None:
    raw_dir = tmp_path / "data/raw/live/comtrade_availability"
    raw_dir.mkdir(parents=True)
    (raw_dir / "sample.metadata.json").write_text(
        json.dumps(
            {
                "parameters": {
                    "year": 1962,
                    "flow_code": "X",
                    "classification_code": "S1",
                    "partner_codes": [0, 24],
                }
            }
        ),
        encoding="utf-8",
    )
    frame = pd.DataFrame(
        [
            {"year": 1962, "flow_code": "X", "classification_code": "S1"},
            {"year": 1963, "flow_code": "X", "classification_code": "S1"},
        ]
    )

    snapshots = _snapshot_partner_codes_by_coverage_request(tmp_path)
    result = _apply_comtrade_snapshot_status(frame, tmp_path, (0, 24, 251))

    assert snapshots[(1962, "X", "S1")] == (0, 24)
    assert result.loc[0, "snapshot_status"] == "stale_against_current_configuration"
    assert result.loc[1, "snapshot_status"] == ""


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


def _write_local_diagnostic_inputs(root: Path) -> None:
    config = root / "config"
    config.mkdir(exist_ok=True)
    (config / "comtrade.yml").write_text(
        """
comtrade:
  coverage_classification_codes: [S1]
  preferred_coverage_classification_codes: [S1]
  reporter_code: 620
  flow_codes: [X]
  commodity_codes: [TOTAL]
  years: [1962]
  partner_codes: [0, 24]
  classification_code: S1
  max_records: 500
""",
        encoding="utf-8",
    )
    (config / "partner_groups.yml").write_text(
        """
groups:
  colonies:
    members:
      - {code: 24, name: Angola, start_year: 1960, end_year: 1973}
  efta:
    members: []
  eec:
    members: []
""",
        encoding="utf-8",
    )
    (config / "bpstat_series.yml").write_text(
        """
series: []
reviewed_candidates:
  - slug: population
    series_id: 1
    concept: population
    label: Population
    domain_id: 13
    dataset_id: dataset
    frequency: annual
    units: people
    price_basis: not_applicable
    first_observation: "1960-01-01"
    last_observation: "1973-01-01"
    territorial_definition: Portugal
    reconstruction_method: source
    methodological_breaks: none_reviewed
    source_status: original
    review_status: accepted_for_context
    rejection_or_hold_reason: none
""",
        encoding="utf-8",
    )
    (config / "manual_sources.yml").write_text(
        """
manual_sources:
  - source_id: ine
    title_pattern: INE
    expected_years: [1962]
    target_template: data/manual/templates/trade_transcription_template.csv
    validation: double_entry
""",
        encoding="utf-8",
    )
    (config / "sitc_industry_mapping.yml").write_text(
        """
classification_revision: SITC Rev.1
mapping_status: pending_official_correspondence
mappings: []
""",
        encoding="utf-8",
    )
    matrix_dir = root / "data/interim/live"
    matrix_dir.mkdir(parents=True)
    pd.DataFrame(
        [
            {
                "year": 1962,
                "flow_code": "X",
                "classification_code": "S1",
                "reporter_code": 620,
                "partner_code": 0,
                "partner_desc": "World",
                "commodity_code_source": "TOTAL",
                "trade_value_usd": 100.0,
                "is_world_record": True,
                "raw_records": 2,
                "duplicate_key": False,
            },
            {
                "year": 1962,
                "flow_code": "X",
                "classification_code": "S1",
                "reporter_code": 620,
                "partner_code": 24,
                "partner_desc": "Angola",
                "commodity_code_source": "TOTAL",
                "trade_value_usd": 20.0,
                "is_world_record": False,
                "raw_records": 2,
                "duplicate_key": False,
            },
        ]
    ).to_csv(matrix_dir / "comtrade_coverage_matrix.csv", index=False)
