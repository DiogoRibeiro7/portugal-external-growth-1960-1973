"""End-to-end extraction, transformation, and validation orchestration."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from portugal_external_growth.aggregate_orientation import (
    build_validated_aggregate_orientation_outputs,
)
from portugal_external_growth.clients.bpstat import BPstatClient, BPstatSeries
from portugal_external_growth.clients.comtrade import (
    ComtradeClient,
    ComtradeProductRequest,
    ComtradeRequest,
)
from portugal_external_growth.clients.world_bank import WorldBankClient, WorldBankRequest
from portugal_external_growth.config import load_yaml
from portugal_external_growth.data_dictionary import build_analytical_data_dictionary
from portugal_external_growth.descriptive import build_descriptive_trade_results
from portugal_external_growth.efta_policy import build_efta_policy_outputs
from portugal_external_growth.empirical import (
    build_empirical_prerequisite_status,
    build_empirical_readiness_audit,
    build_empirical_readiness_audit_notes,
    build_empirical_risk_notes,
    build_model_specification_registry,
    empty_coefficients,
    empty_diagnostics,
    empty_identification_strategy_review,
    load_empirical_design_matrix_or_empty,
    load_sectoral_output_panel_or_empty,
    load_sectoral_output_source_registry_or_empty,
    load_sectoral_output_source_transition_registry_or_empty,
)
from portugal_external_growth.http import build_session
from portugal_external_growth.industry_exposure import build_industry_exposure_outputs
from portugal_external_growth.io_utils import (
    sha256_file,
    write_text_lf,
)
from portugal_external_growth.io_utils import (
    write_dataframe_with_metadata as _write_dataframe_with_metadata,
)
from portugal_external_growth.macro import build_bpstat_macro_outputs
from portugal_external_growth.manual import (
    build_ine_harmonised,
    compare_ine_transcriptions,
    init_ine_transcription,
    initialise_templates,
    prepare_ine_transcription_workflow,
)
from portugal_external_growth.mapping import build_mapping_outputs
from portugal_external_growth.partners import (
    annotate_comtrade_partner_areas,
    build_requested_partner_return_status,
    configured_comtrade_partner_codes,
    load_historical_group_memberships,
    partner_codes_sha256,
)
from portugal_external_growth.product_industry_mapping import (
    build_product_industry_mapping_outputs,
)
from portugal_external_growth.product_trade import (
    build_product_extraction_design_outputs,
    product_source_files,
)
from portugal_external_growth.reconciliation import (
    build_exchange_rate_evidence,
    build_ine_comtrade_1962_notes,
    build_ine_comtrade_1962_reconciliation,
    build_reconciliation_registry,
    build_trade_reconciliation_notes,
    build_trade_source_comparison,
    finalise_trade_reconciliation,
)
from portugal_external_growth.registry import (
    build_bpstat_registry_review,
    load_bpstat_reviewed_candidates,
)
from portugal_external_growth.release_freeze import (
    build_research_data_freeze_outputs,
    build_source_release_policy,
)
from portugal_external_growth.settings import Settings
from portugal_external_growth.transforms import (
    compile_comtrade_coverage_audit,
    load_territorial_definition_registry,
    normalise_comtrade,
    summarise_gdp_growth,
)
from portugal_external_growth.validation import (
    ValidationIssue,
    build_file_manifest,
    build_manual_source_document_inventory,
    build_research_readiness_report,
    build_scoped_file_manifest,
    has_error,
    issues_to_frame,
    validate_manual_transcription_source_hashes,
    validate_preliminary_trade_shares,
    validate_unique,
    validate_year_range,
)


def write_dataframe_with_metadata(
    frame: pd.DataFrame,
    csv_path: Path,
    *,
    metadata: Mapping[str, Any],
    overwrite: bool = True,
) -> Path:
    """Write pipeline metadata relative to the repository root implied by the output path."""

    return _write_dataframe_with_metadata(
        frame,
        csv_path,
        metadata=metadata,
        overwrite=overwrite,
        root=_pipeline_metadata_root(csv_path),
    )


def _pipeline_metadata_root(csv_path: Path) -> Path:
    resolved = csv_path.resolve()
    configured_root = os.getenv("PEG_ROOT")
    if configured_root:
        candidate = Path(configured_root).expanduser().resolve()
        try:
            resolved.relative_to(candidate)
        except ValueError:
            pass
        else:
            return candidate
    for candidate in [resolved.parent, *resolved.parents]:
        if (candidate / "pyproject.toml").exists() or (candidate / "config/project.yml").exists():
            return candidate
    for marker in ("data", "results", "config", "prompts", "src", "tests", ".github"):
        if marker not in resolved.parts:
            continue
        index = len(resolved.parts) - 1 - list(reversed(resolved.parts)).index(marker)
        if index > 0:
            return Path(*resolved.parts[:index])
    return Path.cwd()


def bootstrap(root: Path) -> None:
    """Rebuild deterministic outputs from the committed bootstrap snapshot."""

    source = root / "data/raw/bootstrap/world_bank_gdp_growth_portugal_1961_1973.csv"
    frame = pd.read_csv(source)
    interim = frame.rename(columns={"indicator": "indicator_name"})
    write_dataframe_with_metadata(
        interim,
        root / "data/interim/bootstrap/world_bank_macro_long.csv",
        metadata={"source_files": [str(source)], "stage": "normalised_bootstrap"},
    )
    summary = summarise_gdp_growth(frame)
    write_dataframe_with_metadata(
        summary,
        root / "data/processed/bootstrap/portugal_gdp_growth_summary.csv",
        metadata={"source_files": [str(source)], "stage": "processed_bootstrap"},
    )
    coverage = pd.DataFrame(
        [
            {
                "dataset": "world_bank_gdp_growth",
                "status": "bootstrap_available",
                "start_year": int(frame["year"].min()),
                "end_year": int(frame["year"].max()),
                "rows": len(frame),
                "empirical": True,
                "production_refresh_required": True,
            },
            {
                "dataset": "un_comtrade_trade",
                "status": "live_extraction_required",
                "start_year": 1962,
                "end_year": 1973,
                "rows": 0,
                "empirical": True,
                "production_refresh_required": True,
            },
            {
                "dataset": "bpstat_macro",
                "status": "series_registry_required",
                "start_year": 1960,
                "end_year": 1973,
                "rows": 0,
                "empirical": True,
                "production_refresh_required": True,
            },
        ]
    )
    write_dataframe_with_metadata(
        coverage,
        root / "results/bootstrap/data_coverage_status.csv",
        metadata={"stage": "bootstrap_status"},
    )
    validation = validate_unique(frame, ["country_code", "indicator_code", "year"], name="gdp")
    validation += validate_year_range(
        frame, year_column="year", start_year=1960, end_year=1973, name="gdp"
    )
    validation_frame = issues_to_frame(validation)
    write_dataframe_with_metadata(
        validation_frame,
        root / "results/bootstrap/validation_report.csv",
        metadata={"stage": "bootstrap_validation"},
    )
    summary_row = summary.iloc[0]
    text = (
        "BOOTSTRAP CROSS-CHECK REPORT\n"
        "============================\n"
        f"GDP growth observations: {int(summary_row['observations'])}\n"
        f"Period: {int(summary_row['start_year'])}-{int(summary_row['end_year'])}\n"
        f"Arithmetic mean annual growth: {summary_row['arithmetic_mean_growth_percent']:.6f}%\n"
        f"Median annual growth: {summary_row['median_growth_percent']:.6f}%\n"
        f"Cumulative real GDP index (start=100): "
        f"{summary_row['cumulative_real_gdp_index_start_100']:.6f}\n"
        "Trade results: NOT YET PRODUCED; live Comtrade or transcribed INE data required.\n"
        "BPstat results: NOT YET PRODUCED; reviewed series registry required.\n"
    )
    output = root / "results/bootstrap/cross_checks.txt"
    write_text_lf(output, text)
    manifest = build_scoped_file_manifest(
        root,
        [
            "data/raw/bootstrap/world_bank_gdp_growth_portugal_1961_1973.csv",
            "data/interim/bootstrap/world_bank_macro_long.csv",
            "data/interim/bootstrap/world_bank_macro_long.csv.metadata.json",
            "data/processed/bootstrap/portugal_gdp_growth_summary.csv",
            "data/processed/bootstrap/portugal_gdp_growth_summary.csv.metadata.json",
            "results/bootstrap/data_coverage_status.csv",
            "results/bootstrap/data_coverage_status.csv.metadata.json",
            "results/bootstrap/validation_report.csv",
            "results/bootstrap/validation_report.csv.metadata.json",
            "results/bootstrap/cross_checks.txt",
        ],
    )
    write_dataframe_with_metadata(
        manifest,
        root / "results/manifests/bootstrap_manifest.csv",
        metadata={"stage": "manifest", "scope": "bootstrap"},
    )


def extract_world_bank(settings: Settings, *, overwrite: bool) -> None:
    """Extract every configured World Bank indicator."""

    root = settings.resolved_root()
    payload = load_yaml(root / "config/world_bank_indicators.yml")
    indicators = payload.get("indicators")
    if not isinstance(indicators, dict):
        raise TypeError("world_bank_indicators.yml is invalid")
    client = WorldBankClient(build_session(), settings.http_timeout_seconds)
    for indicator_code in indicators:
        request = WorldBankRequest(
            "PRT",
            str(indicator_code),
            settings.start_year,
            settings.end_year,
        )
        raw, frame, url, http_metadata = client.fetch(request)
        client.save(request, raw, frame, url, http_metadata, root, overwrite=overwrite)


def extract_comtrade(settings: Settings, *, overwrite: bool) -> None:
    """Extract bounded annual Comtrade requests from configuration."""

    root = settings.resolved_root()
    payload = load_yaml(root / "config/comtrade.yml")
    config = payload.get("comtrade")
    if not isinstance(config, dict):
        raise TypeError("comtrade.yml is invalid")
    client = ComtradeClient(
        build_session(),
        timeout_seconds=settings.http_timeout_seconds,
        subscription_key=settings.comtrade_subscription_key,
    )
    years = tuple(int(year) for year in config["years"])
    partners = configured_comtrade_partner_codes(root, years)
    for year in years:
        for flow_code in config["flow_codes"]:
            request = ComtradeRequest(
                year=int(year),
                reporter_code=int(config["reporter_code"]),
                partner_codes=partners,
                flow_code=str(flow_code),
                commodity_code=str(config["commodity_codes"][0]),
                classification_code=str(config["classification_code"]),
                max_records=int(config["max_records"]),
            )
            raw, frame, url, http_metadata = client.fetch(request)
            client.save(request, raw, frame, url, http_metadata, root, overwrite=overwrite)


def extract_comtrade_products(settings: Settings, *, overwrite: bool) -> None:
    """Extract subscription-key product-level Comtrade snapshots."""

    if not settings.comtrade_subscription_key:
        raise ValueError("COMTRADE_SUBSCRIPTION_KEY is required for product-level extraction.")
    root = settings.resolved_root()
    payload = load_yaml(root / "config/comtrade.yml")
    config = payload.get("comtrade")
    if not isinstance(config, dict):
        raise TypeError("comtrade.yml is invalid")
    product = config.get("product_extraction")
    if not isinstance(product, dict):
        raise TypeError("comtrade.yml is missing product_extraction")
    commodity_batches = product.get("commodity_code_batches", [])
    if not isinstance(commodity_batches, list):
        commodity_batches = []
    batches = [
        tuple(str(code) for code in batch)
        for batch in commodity_batches
        if isinstance(batch, list) and batch
    ]
    if not batches:
        raise ValueError("Register product_extraction.commodity_code_batches before extraction.")
    client = ComtradeClient(
        build_session(),
        timeout_seconds=settings.http_timeout_seconds,
        subscription_key=settings.comtrade_subscription_key,
    )
    years_value = product.get("years", config.get("years", []))
    flows_value = product.get("flow_codes", config.get("flow_codes", []))
    partners_value = product.get("partner_codes", [0])
    years = [int(year) for year in years_value] if isinstance(years_value, list) else []
    flows = [str(flow) for flow in flows_value] if isinstance(flows_value, list) else []
    partners = [int(code) for code in partners_value] if isinstance(partners_value, list) else []
    reporter_code = int(str(product.get("reporter_code", config.get("reporter_code", 620))))
    classification_code = str(
        product.get("classification_code", config.get("classification_code", "S1"))
    )
    aggregate_by = product.get("aggregate_by")
    for year in years:
        for flow_code in flows:
            for partner_code in partners:
                for commodity_codes in batches:
                    request = ComtradeProductRequest(
                        year=year,
                        reporter_code=reporter_code,
                        partner_code=partner_code,
                        flow_code=flow_code,
                        commodity_codes=commodity_codes,
                        classification_code=classification_code,
                        max_records=int(product.get("max_records", 250000)),
                        aggregate_by=aggregate_by if isinstance(aggregate_by, str) else None,
                        breakdown_mode=str(product.get("breakdown_mode", "classic")),
                        include_desc=bool(product.get("include_desc", True)),
                    )
                    raw, frame, url, http_metadata = client.fetch_product(request)
                    client.save_product_response(
                        request,
                        raw,
                        frame,
                        url,
                        http_metadata,
                        root,
                        overwrite=overwrite,
                    )


def audit_comtrade_coverage(settings: Settings, *, overwrite: bool) -> None:
    """Audit Portugal's historical UN Comtrade coverage before analytical use."""

    root = settings.resolved_root()
    payload = load_yaml(root / "config/comtrade.yml")
    config = payload.get("comtrade")
    if not isinstance(config, dict):
        raise TypeError("comtrade.yml is invalid")

    client = ComtradeClient(
        build_session(),
        timeout_seconds=settings.http_timeout_seconds,
        subscription_key=settings.comtrade_subscription_key,
    )
    classification_codes = tuple(config.get("coverage_classification_codes", ["S1", "S2"]))
    preferred_classification_codes = tuple(
        str(value) for value in config.get("preferred_coverage_classification_codes", ["S1", "S2"])
    )
    years = tuple(int(year) for year in config["years"])
    flows = tuple(str(flow_code) for flow_code in config["flow_codes"])
    partners = configured_comtrade_partner_codes(root, years)
    request_snapshot_fields = _comtrade_request_snapshot_fields(root, partners, partners)

    matrix_inputs: list[pd.DataFrame] = []
    raw_paths: list[str] = []
    for classification_code in classification_codes:
        for year in years:
            for flow_code in flows:
                request = ComtradeRequest(
                    year=year,
                    reporter_code=int(config["reporter_code"]),
                    partner_codes=partners,
                    flow_code=flow_code,
                    commodity_code=str(config["commodity_codes"][0]),
                    classification_code=str(classification_code),
                    max_records=int(config["max_records"]),
                )
                raw, frame, url, http_metadata = client.fetch(request)
                raw_path = client.save_availability_response(
                    request,
                    raw,
                    frame,
                    url,
                    http_metadata,
                    root,
                    overwrite=overwrite,
                )
                raw_paths.append(str(raw_path))
                if frame.empty:
                    matrix_inputs.append(
                        pd.DataFrame(
                            [
                                {
                                    "year": year,
                                    "flow_code": flow_code,
                                    "classification_code": classification_code,
                                    "reporter_code": int(config["reporter_code"]),
                                    "partner_code": pd.NA,
                                    "partner_desc": "",
                                    "commodity_code_source": str(config["commodity_codes"][0]),
                                    "trade_value_usd": pd.NA,
                                    "is_world_record": False,
                                    "raw_records": 0,
                                    **request_snapshot_fields,
                                }
                            ]
                        )
                    )
                    continue

                normalised = normalise_comtrade(frame)
                matrix = pd.DataFrame(
                    {
                        "year": normalised["year"],
                        "flow_code": normalised["flow_code"],
                        "classification_code": classification_code,
                        "reporter_code": int(config["reporter_code"]),
                        "partner_code": normalised["partner_code"],
                        "partner_desc": normalised["partner_desc"],
                        "commodity_code_source": normalised["commodity_code"],
                        "trade_value_usd": normalised["trade_value_usd"],
                        "cif_value_usd": normalised["cif_value_usd"],
                        "fob_value_usd": normalised["fob_value_usd"],
                        "is_reported": normalised["is_reported"],
                        "is_original_classification": normalised["is_original_classification"],
                        "legacy_estimation_flag": normalised["legacy_estimation_flag"],
                        "is_world_record": normalised["partner_code"].eq(0),
                        "raw_records": len(frame),
                        **request_snapshot_fields,
                    }
                )
                area_path = root / "config/comtrade_partner_areas.yml"
                if area_path.exists():
                    matrix = annotate_comtrade_partner_areas(matrix, area_path)
                matrix_inputs.append(matrix)

    coverage_matrix, audit, notes = compile_comtrade_coverage_audit(
        matrix_inputs,
        colonial_partner_codes=_colonial_partner_codes(root),
        expected_years=years,
        expected_flow_codes=flows,
        preferred_classification_codes=preferred_classification_codes,
        territorial_definitions=load_territorial_definition_registry(
            root / "config/territorial_definitions.yml"
        ),
    )
    write_dataframe_with_metadata(
        coverage_matrix,
        root / "data/interim/live/comtrade_coverage_matrix.csv",
        metadata={"source_files": raw_paths, "stage": "comtrade_coverage_matrix"},
    )
    write_dataframe_with_metadata(
        audit,
        root / "results/diagnostics/comtrade_coverage/comtrade_coverage_audit.csv",
        metadata={
            "source_files": [
                "data/interim/live/comtrade_coverage_matrix.csv",
                "config/territorial_definitions.yml",
            ]
        },
    )
    area_path = root / "config/comtrade_partner_areas.yml"
    if area_path.exists():
        requested_status = build_requested_partner_return_status(
            coverage_matrix,
            area_path,
            years=years,
            flows=flows,
            classification_codes=classification_codes,
            configured_partner_codes=partners,
        )
        write_dataframe_with_metadata(
            requested_status.loc[~requested_status["returned"]].copy(),
            root / "results/diagnostics/comtrade_coverage/requested_not_returned.csv",
            metadata={
                "source_files": [
                    "data/interim/live/comtrade_coverage_matrix.csv",
                    "config/comtrade_partner_areas.yml",
                ]
            },
        )
    notes_path = root / "results/diagnostics/comtrade_coverage/comtrade_coverage_notes.txt"
    write_text_lf(notes_path, notes)


def rebuild_comtrade_coverage_audit_from_local(settings: Settings) -> None:
    """Regenerate Comtrade coverage-audit outputs from committed local snapshots."""

    root = settings.resolved_root()
    matrix_path = root / "data/interim/live/comtrade_coverage_matrix.csv"
    raw_snapshot_dir = root / "data/raw/live/comtrade_availability"
    if not matrix_path.exists() and not raw_snapshot_dir.exists():
        return
    payload = load_yaml(root / "config/comtrade.yml")
    config = payload.get("comtrade")
    if not isinstance(config, dict):
        raise TypeError("comtrade.yml is invalid")
    years = tuple(int(year) for year in config["years"])
    flows = tuple(str(flow_code) for flow_code in config["flow_codes"])
    partners = configured_comtrade_partner_codes(root, years)
    preferred_classification_codes = tuple(
        str(value) for value in config.get("preferred_coverage_classification_codes", ["S1", "S2"])
    )
    area_path = root / "config/comtrade_partner_areas.yml"
    matrix_inputs = _local_comtrade_coverage_matrices(root, partners)
    if not matrix_inputs:
        coverage_matrix = pd.read_csv(matrix_path)
        if "commodity_code_source" not in coverage_matrix.columns:
            coverage_matrix["commodity_code_source"] = str(config["commodity_codes"][0])
        if area_path.exists():
            coverage_matrix = annotate_comtrade_partner_areas(coverage_matrix, area_path)
        coverage_matrix = _apply_comtrade_snapshot_status(coverage_matrix, root, partners)
        matrix_inputs = [coverage_matrix]
    coverage_matrix, audit, notes = compile_comtrade_coverage_audit(
        matrix_inputs,
        colonial_partner_codes=_colonial_partner_codes(root),
        expected_years=years,
        expected_flow_codes=flows,
        preferred_classification_codes=preferred_classification_codes,
        territorial_definitions=load_territorial_definition_registry(
            root / "config/territorial_definitions.yml"
        ),
    )
    write_dataframe_with_metadata(
        coverage_matrix,
        matrix_path,
        metadata={
            "source_files": _existing_metadata_source_files(matrix_path),
            "stage": "comtrade_coverage_matrix",
        },
    )
    write_dataframe_with_metadata(
        audit,
        root / "results/diagnostics/comtrade_coverage/comtrade_coverage_audit.csv",
        metadata={
            "source_files": [
                "data/interim/live/comtrade_coverage_matrix.csv",
                "config/territorial_definitions.yml",
            ]
        },
    )
    if area_path.exists():
        classification_codes = tuple(
            str(value) for value in config.get("coverage_classification_codes", ["S1", "S2"])
        )
        requested_status = build_requested_partner_return_status(
            coverage_matrix,
            area_path,
            years=years,
            flows=flows,
            classification_codes=classification_codes,
            configured_partner_codes=partners,
            snapshot_partner_codes=_snapshot_partner_codes_by_coverage_request(root),
        )
        write_dataframe_with_metadata(
            requested_status.loc[~requested_status["returned"]].copy(),
            root / "results/diagnostics/comtrade_coverage/requested_not_returned.csv",
            metadata={
                "source_files": [
                    "data/interim/live/comtrade_coverage_matrix.csv",
                    "config/comtrade_partner_areas.yml",
                ]
            },
        )
    notes_path = root / "results/diagnostics/comtrade_coverage/comtrade_coverage_notes.txt"
    write_text_lf(notes_path, notes)


def _colonial_partner_codes(root: Path) -> tuple[int, ...]:
    historical = root / "config/historical_groups.yml"
    areas = root / "config/comtrade_partner_areas.yml"
    if historical.exists() and areas.exists():
        memberships = load_historical_group_memberships(historical, areas)
        return tuple(
            sorted(
                int(code)
                for code in memberships.loc[
                    memberships["partner_group"].eq("colonies"), "partner_code"
                ]
                .dropna()
                .unique()
                .tolist()
            )
        )
    partner_groups = load_yaml(root / "config/partner_groups.yml")
    return tuple(
        int(member["code"])
        for group_name, group in partner_groups["groups"].items()
        if group_name == "colonies" and isinstance(group, dict)
        for member in group.get("members", [])
        if isinstance(member, dict)
    )


def _comtrade_request_snapshot_fields(
    root: Path,
    snapshot_partner_codes: tuple[int, ...],
    configured_partner_codes: tuple[int, ...],
) -> dict[str, str]:
    snapshot_codes = tuple(sorted(snapshot_partner_codes))
    configured_codes = tuple(sorted(configured_partner_codes))
    area_path = root / "config/comtrade_partner_areas.yml"
    config_path = root / "config/comtrade.yml"
    return {
        "snapshot_partner_codes": ",".join(str(code) for code in snapshot_codes),
        "request_partner_codes_sha256": partner_codes_sha256(snapshot_codes),
        "partner_area_registry_sha256": sha256_file(area_path) if area_path.exists() else "",
        "comtrade_config_sha256": sha256_file(config_path) if config_path.exists() else "",
        "snapshot_status": (
            "current_against_configuration"
            if snapshot_codes == configured_codes
            else "stale_against_current_configuration"
        ),
    }


def _local_comtrade_coverage_matrices(
    root: Path,
    configured_partner_codes: tuple[int, ...],
) -> list[pd.DataFrame]:
    matrices: list[pd.DataFrame] = []
    area_path = root / "config/comtrade_partner_areas.yml"
    for raw_path in sorted((root / "data/raw/live/comtrade_availability").glob("*.json")):
        metadata_path = raw_path.with_suffix(".metadata.json")
        if not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        parameters = metadata.get("parameters")
        if not isinstance(parameters, dict):
            continue
        year = int(parameters["year"])
        flow_code = str(parameters["flow_code"])
        classification_code = str(parameters["classification_code"])
        commodity_code = str(parameters.get("commodity_code", "TOTAL"))
        reporter_code = int(parameters["reporter_code"])
        partner_codes = parameters.get("partner_codes")
        if not isinstance(partner_codes, list):
            continue
        snapshot_codes = tuple(sorted(int(code) for code in partner_codes))
        snapshot_fields = _comtrade_request_snapshot_fields(
            root,
            snapshot_codes,
            configured_partner_codes,
        )
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            continue
        if not data:
            matrices.append(
                pd.DataFrame(
                    [
                        {
                            "year": year,
                            "flow_code": flow_code,
                            "classification_code": classification_code,
                            "reporter_code": reporter_code,
                            "partner_code": pd.NA,
                            "partner_desc": "",
                            "commodity_code_source": commodity_code,
                            "trade_value_usd": pd.NA,
                            "cif_value_usd": pd.NA,
                            "fob_value_usd": pd.NA,
                            "is_reported": pd.NA,
                            "is_original_classification": pd.NA,
                            "legacy_estimation_flag": pd.NA,
                            "is_world_record": False,
                            "raw_records": 0,
                            **snapshot_fields,
                        }
                    ]
                )
            )
            continue
        normalised = normalise_comtrade(pd.json_normalize(data))
        matrix = pd.DataFrame(
            {
                "year": normalised["year"],
                "flow_code": normalised["flow_code"],
                "classification_code": classification_code,
                "reporter_code": reporter_code,
                "partner_code": normalised["partner_code"],
                "partner_desc": normalised["partner_desc"],
                "commodity_code_source": normalised["commodity_code"],
                "trade_value_usd": normalised["trade_value_usd"],
                "cif_value_usd": normalised["cif_value_usd"],
                "fob_value_usd": normalised["fob_value_usd"],
                "is_reported": normalised["is_reported"],
                "is_original_classification": normalised["is_original_classification"],
                "legacy_estimation_flag": normalised["legacy_estimation_flag"],
                "is_world_record": normalised["partner_code"].eq(0),
                "raw_records": len(data),
                **snapshot_fields,
            }
        )
        if area_path.exists():
            matrix = annotate_comtrade_partner_areas(matrix, area_path)
        matrices.append(matrix)
    return matrices


def _apply_comtrade_snapshot_status(
    coverage_matrix: pd.DataFrame,
    root: Path,
    configured_partner_codes: tuple[int, ...],
) -> pd.DataFrame:
    snapshots = _snapshot_partner_codes_by_coverage_request(root)
    if not snapshots:
        return coverage_matrix
    output = coverage_matrix.copy()
    for column in (
        "snapshot_partner_codes",
        "request_partner_codes_sha256",
        "partner_area_registry_sha256",
        "comtrade_config_sha256",
        "snapshot_status",
    ):
        if column not in output:
            output[column] = ""
    for index, row in output.iterrows():
        key = (int(row["year"]), str(row["flow_code"]), str(row["classification_code"]))
        snapshot_codes = snapshots.get(key)
        if snapshot_codes is None:
            continue
        fields = _comtrade_request_snapshot_fields(root, snapshot_codes, configured_partner_codes)
        for column, value in fields.items():
            output.at[index, column] = value
    return output


def _snapshot_partner_codes_by_coverage_request(
    root: Path,
) -> dict[tuple[int, str, str], tuple[int, ...]]:
    snapshots: dict[tuple[int, str, str], tuple[int, ...]] = {}
    for path in sorted((root / "data/raw/live/comtrade_availability").glob("*.metadata.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        parameters = payload.get("parameters")
        if not isinstance(parameters, dict):
            continue
        partner_codes = parameters.get("partner_codes")
        if not isinstance(partner_codes, list):
            continue
        key = (
            int(parameters["year"]),
            str(parameters["flow_code"]),
            str(parameters["classification_code"]),
        )
        snapshots[key] = tuple(sorted(int(code) for code in partner_codes))
    return snapshots


def _existing_metadata_source_files(path: Path) -> list[str]:
    sidecar = path.with_suffix(path.suffix + ".metadata.json")
    if not sidecar.exists():
        return []
    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    source_files = payload.get("source_files")
    if not isinstance(source_files, list):
        return []
    return [str(source_file) for source_file in source_files]


def _load_bpstat_registry(path: Path) -> list[BPstatSeries]:
    payload = load_yaml(path)
    series_payload = payload.get("series")
    if not isinstance(series_payload, list):
        raise TypeError("bpstat_series.yml must contain a series list")
    return [BPstatSeries(**item) for item in series_payload if isinstance(item, dict)]


def extract_bpstat(settings: Settings, *, overwrite: bool) -> None:
    """Extract BPstat series after the registry has been manually reviewed."""

    root = settings.resolved_root()
    registry = _load_bpstat_registry(root / "config/bpstat_series.yml")
    if not registry:
        print("BPstat extraction skipped: config/bpstat_series.yml has no reviewed series.")
        return
    client = BPstatClient(build_session(), settings.http_timeout_seconds)
    ids = tuple(item.series_id for item in registry)
    metadata = client.fetch_series_metadata(ids)
    grouped: dict[int, tuple[int, str]] = {}
    for item in metadata:
        domain_ids = item.get("domain_ids")
        dataset_id = item.get("dataset_id")
        series_id = item.get("id") or item.get("series_id")
        if not isinstance(domain_ids, list) or not domain_ids:
            raise ValueError("BPstat metadata is missing domain_ids")
        if not isinstance(dataset_id, str) or not isinstance(series_id, int):
            raise ValueError("BPstat metadata is missing dataset_id or series identifier")
        grouped[series_id] = (int(domain_ids[0]), dataset_id)
    for series_id in ids:
        domain_id, dataset_id = grouped[series_id]
        series_ids = (series_id,)
        raw, frame, url, http_metadata = client.fetch_dataset(
            domain_id=domain_id, dataset_id=dataset_id, series_ids=series_ids
        )
        client.save(
            raw_json=raw,
            frame=frame,
            request_url=url,
            http_metadata=http_metadata,
            series_ids=series_ids,
            root=root,
            overwrite=overwrite,
        )


def review_bpstat_registry(settings: Settings) -> None:
    """Write the reviewed BPstat candidate registry and review report."""

    root = settings.resolved_root()
    registry = load_bpstat_reviewed_candidates(root / "config/bpstat_series.yml")
    write_dataframe_with_metadata(
        registry,
        root / "data/interim/live/bpstat_series_registry.csv",
        metadata={
            "source_files": ["config/bpstat_series.yml"],
            "stage": "bpstat_series_registry_review",
        },
    )
    report = build_bpstat_registry_review(registry)
    output = root / "results/live/bpstat_registry_review.txt"
    write_text_lf(output, report)


def build(settings: Settings) -> None:
    """Build all processed tables for sources currently available locally."""

    root = settings.resolved_root()
    bootstrap(root)

    trade_files = sorted((root / "data/raw/live/comtrade").glob("*.csv"))
    if trade_files:
        frames = [pd.read_csv(path) for path in trade_files]
        normalised = normalise_comtrade(pd.concat(frames, ignore_index=True))
        write_dataframe_with_metadata(
            normalised,
            root / "data/interim/live/comtrade_normalised.csv",
            metadata={"source_files": [str(path) for path in trade_files]},
        )
    if (root / "data/interim/live/comtrade_coverage_matrix.csv").exists():
        build_descriptive_results(settings)
    if sorted((root / "data/raw/live/bpstat").glob("series_*.csv")):
        build_bpstat_macro(settings)


def build_bpstat_macro(settings: Settings) -> None:
    """Build BPstat macro and broad-sector context outputs."""

    root = settings.resolved_root()
    normalised, macro, broad_sector, dictionary, validation, notes = build_bpstat_macro_outputs(
        root
    )
    raw_files = [
        *sorted((root / "data/raw/live/bpstat").glob("series_*.json")),
        *sorted((root / "data/raw/live/bpstat").glob("series_*.csv")),
    ]
    source_files = [
        "data/interim/live/bpstat_series_registry.csv",
        *[path.relative_to(root).as_posix() for path in raw_files],
    ]
    write_dataframe_with_metadata(
        normalised,
        root / "data/interim/live/bpstat_macro_long.csv",
        metadata={"source_files": source_files, "stage": "bpstat_macro_normalised_long"},
    )
    write_dataframe_with_metadata(
        macro,
        root / "data/processed/live/portugal_macro_context.csv",
        metadata={
            "source_files": ["data/interim/live/bpstat_macro_long.csv"],
            "stage": "bpstat_macro_context_processed",
        },
    )
    write_dataframe_with_metadata(
        build_analytical_data_dictionary(
            "data/processed/live/portugal_macro_context.csv",
            macro,
        ),
        root / "results/live/portugal_macro_context_data_dictionary.csv",
        metadata={
            "source_files": ["data/processed/live/portugal_macro_context.csv"],
            "stage": "portugal_macro_context_data_dictionary",
        },
    )
    write_dataframe_with_metadata(
        broad_sector,
        root / "data/processed/live/portugal_broad_sector_context.csv",
        metadata={
            "source_files": [
                "data/interim/live/bpstat_macro_long.csv",
                "data/processed/live/portugal_macro_context.csv",
            ],
            "stage": "bpstat_broad_sector_context_processed",
        },
    )
    write_dataframe_with_metadata(
        build_analytical_data_dictionary(
            "data/processed/live/portugal_broad_sector_context.csv",
            broad_sector,
        ),
        root / "results/live/portugal_broad_sector_context_data_dictionary.csv",
        metadata={
            "source_files": ["data/processed/live/portugal_broad_sector_context.csv"],
            "stage": "portugal_broad_sector_context_data_dictionary",
        },
    )
    write_dataframe_with_metadata(
        dictionary,
        root / "results/live/bpstat_macro_data_dictionary.csv",
        metadata={"source_files": ["data/interim/live/bpstat_series_registry.csv"]},
    )
    write_dataframe_with_metadata(
        validation,
        root / "results/validation/bpstat_macro_validation_report.csv",
        metadata={
            "source_files": [
                "data/interim/live/bpstat_macro_long.csv",
                "data/interim/live/bpstat_series_registry.csv",
            ],
            "stage": "bpstat_macro_validation",
        },
    )
    write_text_lf(root / "results/live/bpstat_macro_cross_checks.txt", notes)


def design_product_comtrade_extraction(settings: Settings) -> None:
    """Build guarded product-level Comtrade extraction design outputs."""

    root = settings.resolved_root()
    plan, product, coverage, world_reconciliation, status, notes = (
        build_product_extraction_design_outputs(
            root,
            subscription_key_present=bool(settings.comtrade_subscription_key),
        )
    )
    raw_sources = product_source_files(root)
    source_files = ["config/comtrade.yml", *raw_sources]
    write_dataframe_with_metadata(
        plan,
        root / "results/live/comtrade_product_extraction_plan.csv",
        metadata={"source_files": ["config/comtrade.yml"], "stage": "comtrade_product_plan"},
    )
    write_dataframe_with_metadata(
        status,
        root / "results/live/comtrade_product_extraction_status.csv",
        metadata={"source_files": ["results/live/comtrade_product_extraction_plan.csv"]},
    )
    write_dataframe_with_metadata(
        product,
        root / "data/interim/live/comtrade_product_normalised.csv",
        metadata={"source_files": source_files, "stage": "comtrade_product_normalised"},
    )
    write_dataframe_with_metadata(
        coverage,
        root / "results/diagnostics/comtrade_product/product_coverage_diagnostics.csv",
        metadata={"source_files": ["data/interim/live/comtrade_product_normalised.csv"]},
    )
    write_dataframe_with_metadata(
        world_reconciliation,
        root / "results/diagnostics/comtrade_product/product_world_reconciliation.csv",
        metadata={
            "source_files": [
                "data/interim/live/comtrade_product_normalised.csv",
                "data/interim/live/ine_comtrade_1962_reconciliation.csv",
            ],
            "stage": "comtrade_product_world_reconciliation",
        },
    )
    write_text_lf(root / "results/live/comtrade_product_extraction_notes.txt", notes)


def validate(settings: Settings) -> bool:
    """Run local contract checks and write a persistent validation report."""

    root = settings.resolved_root()
    issues: list[ValidationIssue] = []
    gdp_path = root / "data/raw/bootstrap/world_bank_gdp_growth_portugal_1961_1973.csv"
    gdp = pd.read_csv(gdp_path)
    issues += validate_unique(gdp, ["country_code", "indicator_code", "year"], name="gdp")
    issues += validate_year_range(
        gdp,
        year_column="year",
        start_year=settings.start_year,
        end_year=settings.end_year,
        name="gdp",
    )
    preliminary_path = root / "results/live/preliminary_trade_group_shares.csv"
    if preliminary_path.exists():
        preliminary = pd.read_csv(preliminary_path)
        issues += validate_preliminary_trade_shares(preliminary)
    else:
        issues.append(
            ValidationIssue(
                "error",
                "preliminary_trade.available",
                "Missing preliminary World-denominator trade-share table.",
            )
        )
    if (root / "results/live/trade_product_composition.csv").exists():
        issues.append(
            ValidationIssue(
                "error",
                "descriptive.live_product_composition",
                (
                    "Coverage-derived TOTAL product composition must not be published "
                    "under results/live."
                ),
            )
        )
    issues += validate_manual_transcription_source_hashes(root)
    write_dataframe_with_metadata(
        issues_to_frame(issues),
        root / "results/validation/data_integrity_report.csv",
        metadata={"stage": "validation"},
    )
    write_dataframe_with_metadata(
        build_research_readiness_report(root),
        root / "results/validation/research_readiness_report.csv",
        metadata={"stage": "research_readiness"},
    )
    write_dataframe_with_metadata(
        build_manual_source_document_inventory(root),
        root / "results/validation/manual_source_document_inventory.csv",
        metadata={
            "source_files": [
                "config/manual_sources.yml",
                "data/manual/source_documents/source_document_registry.csv",
            ],
            "stage": "manual_source_document_readiness",
        },
    )
    manifest = build_file_manifest(root)
    write_dataframe_with_metadata(
        manifest,
        root / "results/manifests/current_manifest.csv",
        metadata={"stage": "manifest", "scope": "current"},
    )
    return not has_error(issues)


def init_manual_templates(root: Path) -> None:
    """Initialise transcription templates and print created paths."""

    for path in initialise_templates(root):
        print(path)


def prepare_ine_transcription(settings: Settings) -> None:
    """Initialise the controlled INE historical-table transcription workflow."""

    for path in prepare_ine_transcription_workflow(settings.resolved_root()):
        print(path)


def init_ine_transcription_inputs(settings: Settings) -> None:
    """Initialise only protected INE human-entry input files."""

    for path in init_ine_transcription(settings.resolved_root()):
        print(path)


def compare_ine_transcription_passes(settings: Settings) -> None:
    """Regenerate INE double-entry discrepancy outputs."""

    for path in compare_ine_transcriptions(settings.resolved_root()):
        print(path)


def build_ine_harmonised_outputs(settings: Settings) -> None:
    """Regenerate INE harmonisation placeholders pending adjudication."""

    for path in build_ine_harmonised(settings.resolved_root()):
        print(path)


def reconcile_trade_sources(settings: Settings) -> None:
    """Reconcile annual trade totals without silently merging conflicts."""

    root = settings.resolved_root()
    exchange_rate_evidence = build_exchange_rate_evidence(root)
    write_dataframe_with_metadata(
        exchange_rate_evidence,
        root / "data/interim/live/portugal_exchange_rate_evidence.csv",
        metadata={
            "source_files": [
                "data/manual/source_documents/imf_central_banking_legislation_portugal_ch013.pdf"
            ],
            "stage": "exchange_rate_source_evidence",
        },
    )
    ine_comtrade_1962 = build_ine_comtrade_1962_reconciliation(root)
    write_dataframe_with_metadata(
        ine_comtrade_1962,
        root / "data/interim/live/ine_comtrade_1962_reconciliation.csv",
        metadata={
            "source_files": [
                "data/processed/live/ine_aggregate_trade_harmonised.csv",
                "results/diagnostics/comtrade_coverage/comtrade_coverage_audit.csv",
                "data/interim/live/comtrade_coverage_matrix.csv",
                "config/historical_groups.yml",
                "config/comtrade_partner_areas.yml",
                "data/interim/live/historical_colonial_partner_crosswalk.csv",
                "data/interim/live/portugal_exchange_rate_evidence.csv",
            ],
            "stage": "ine_comtrade_1962_reconciliation",
        },
    )
    notes = build_ine_comtrade_1962_notes(ine_comtrade_1962)
    output = root / "results/diagnostics/reconciliation/ine_comtrade_1962_reconciliation.txt"
    write_text_lf(output, notes)
    write_dataframe_with_metadata(
        build_reconciliation_registry(ine_comtrade_1962),
        root / "results/diagnostics/reconciliation/reconciliation_registry.csv",
        metadata={
            "source_files": [
                "data/interim/live/ine_comtrade_1962_reconciliation.csv",
                "results/diagnostics/reconciliation/ine_comtrade_1962_reconciliation.txt",
            ],
            "stage": "reconciliation_readiness_registry",
        },
    )
    comparison = build_trade_source_comparison(root)
    write_dataframe_with_metadata(
        comparison,
        root / "data/interim/live/trade_source_comparison.csv",
        metadata={
            "source_files": [
                "results/diagnostics/comtrade_coverage/comtrade_coverage_audit.csv",
                "data/processed/live/ine_aggregate_trade_harmonised.csv",
                "data/interim/live/portugal_exchange_rate_evidence.csv",
            ],
            "stage": "source_preserving_trade_comparison",
        },
    )
    reconciliation = finalise_trade_reconciliation(comparison)
    write_dataframe_with_metadata(
        reconciliation,
        root / "results/live/trade_reconciliation.csv",
        metadata={"source_files": ["data/interim/live/trade_source_comparison.csv"]},
    )
    notes = build_trade_reconciliation_notes(reconciliation)
    output = root / "results/live/trade_reconciliation_notes.txt"
    write_text_lf(output, notes)


def build_validated_aggregate_orientation(settings: Settings) -> None:
    """Build validated annual aggregate external-orientation outputs."""

    root = settings.resolved_root()
    dataset, status, matrix, source_comparison, notes = (
        build_validated_aggregate_orientation_outputs(root)
    )
    source_files = [
        "data/processed/live/ine_aggregate_trade_harmonised.csv",
        "data/interim/live/ine_comtrade_1962_reconciliation.csv",
        "results/diagnostics/reconciliation/reconciliation_registry.csv",
        "data/manual/transcriptions/pass_1/ine_aggregate_transcription_pass_1.csv",
        "data/manual/transcriptions/pass_2/ine_aggregate_transcription_pass_2.csv",
        "data/manual/source_documents/source_document_registry.csv",
    ]
    write_dataframe_with_metadata(
        dataset,
        root / "data/processed/live/validated_annual_aggregate_external_orientation.csv",
        metadata={
            "source_files": source_files,
            "stage": "validated_annual_aggregate_external_orientation",
        },
    )
    write_dataframe_with_metadata(
        build_analytical_data_dictionary(
            "data/processed/live/validated_annual_aggregate_external_orientation.csv",
            dataset,
        ),
        root / "results/live/validated_annual_aggregate_external_orientation_data_dictionary.csv",
        metadata={
            "source_files": [
                "data/processed/live/validated_annual_aggregate_external_orientation.csv"
            ],
            "stage": "validated_annual_aggregate_external_orientation_data_dictionary",
        },
    )
    write_dataframe_with_metadata(
        status,
        root / "results/live/annual_aggregate_external_orientation_status.csv",
        metadata={"source_files": source_files, "stage": "annual_aggregate_coverage_status"},
    )
    write_dataframe_with_metadata(
        matrix,
        root / "results/live/annual_aggregate_reconciliation_matrix.csv",
        metadata={
            "source_files": [
                "data/interim/live/ine_comtrade_1962_reconciliation.csv",
                "data/processed/live/ine_aggregate_trade_harmonised.csv",
            ],
            "stage": "annual_aggregate_reconciliation_matrix",
        },
    )
    write_dataframe_with_metadata(
        source_comparison,
        root / "results/live/annual_aggregate_source_comparison.csv",
        metadata={
            "source_files": ["data/interim/live/trade_source_comparison.csv"],
            "stage": "annual_aggregate_source_comparison",
        },
    )
    write_text_lf(
        root / "results/live/annual_aggregate_external_orientation_cross_checks.txt", notes
    )


def build_sitc_industry_mapping(settings: Settings) -> None:
    """Build transparent SITC-to-industry mapping outputs."""

    root = settings.resolved_root()
    mapping, unmapped, coverage, broad, narrow = build_mapping_outputs(root)

    raw_registry = pd.DataFrame(
        [
            {
                "source_name": "official_sitc_industry_correspondence",
                "source_status": "not_registered_locally",
                "access_conditions": "to_be_confirmed",
                "licence": "to_be_confirmed",
                "sha256": "",
                "notes": "Register official correspondence before mapping product codes.",
            }
        ]
    )
    write_dataframe_with_metadata(
        raw_registry,
        root / "data/raw/live/sitc_industry_correspondence/source_registry.csv",
        metadata={"stage": "mapping_source_registry"},
    )
    write_dataframe_with_metadata(
        mapping,
        root / "data/interim/live/sitc_industry_mapping.csv",
        metadata={"source_files": ["config/sitc_industry_mapping.yml"]},
    )
    write_dataframe_with_metadata(
        unmapped,
        root / "results/live/sitc_unmapped_codes.csv",
        metadata={"source_files": ["data/interim/live/comtrade_coverage_matrix.csv"]},
    )
    write_dataframe_with_metadata(
        coverage,
        root / "results/live/sitc_mapping_coverage.csv",
        metadata={"source_files": ["results/live/sitc_unmapped_codes.csv"]},
    )
    write_dataframe_with_metadata(
        broad,
        root / "results/live/sitc_mapping_sensitivity_broad.csv",
        metadata={"source_files": ["data/interim/live/sitc_industry_mapping.csv"]},
    )
    write_dataframe_with_metadata(
        narrow,
        root / "results/live/sitc_mapping_sensitivity_narrow.csv",
        metadata={"source_files": ["data/interim/live/sitc_industry_mapping.csv"]},
    )


def build_product_industry_mapping(settings: Settings) -> None:
    """Build guarded product-to-industry mapping outputs."""

    root = settings.resolved_root()
    mapping, unmapped, coverage, panel, reconciliation, status, notes = (
        build_product_industry_mapping_outputs(root)
    )
    source_files = [
        "config/product_industry_mapping.yml",
        "data/interim/live/comtrade_product_normalised.csv",
        "results/live/comtrade_product_extraction_status.csv",
    ]
    write_dataframe_with_metadata(
        mapping,
        root / "data/interim/live/product_industry_mapping.csv",
        metadata={"source_files": ["config/product_industry_mapping.yml"]},
    )
    write_dataframe_with_metadata(
        unmapped,
        root / "results/diagnostics/product_industry_mapping/unmapped_products.csv",
        metadata={"source_files": source_files},
    )
    write_dataframe_with_metadata(
        coverage,
        root / "results/diagnostics/product_industry_mapping/product_mapping_coverage.csv",
        metadata={"source_files": source_files},
    )
    write_dataframe_with_metadata(
        panel,
        root / "data/processed/live/industry_trade_panel.csv",
        metadata={"source_files": source_files},
    )
    write_dataframe_with_metadata(
        build_analytical_data_dictionary(
            "data/processed/live/industry_trade_panel.csv",
            panel,
        ),
        root / "results/live/industry_trade_panel_data_dictionary.csv",
        metadata={
            "source_files": ["data/processed/live/industry_trade_panel.csv"],
            "stage": "industry_trade_panel_data_dictionary",
        },
    )
    write_dataframe_with_metadata(
        reconciliation,
        root / "results/diagnostics/product_industry_mapping/industry_trade_reconciliation.csv",
        metadata={"source_files": source_files},
    )
    write_dataframe_with_metadata(
        status,
        root / "results/diagnostics/product_industry_mapping/product_mapping_status.csv",
        metadata={
            "source_files": [
                "results/diagnostics/product_industry_mapping/product_mapping_coverage.csv",
                "data/processed/live/industry_trade_panel.csv",
            ]
        },
    )
    write_text_lf(root / "results/live/product_industry_mapping_documentation.txt", notes)


def build_descriptive_industry_exposure(settings: Settings) -> None:
    """Build guarded descriptive industry-exposure outputs."""

    root = settings.resolved_root()
    exposures, composition, growth, coverage, status, notes = build_industry_exposure_outputs(root)
    source_files = [
        "data/processed/live/industry_trade_panel.csv",
        "results/diagnostics/product_industry_mapping/product_mapping_status.csv",
    ]
    write_dataframe_with_metadata(
        exposures,
        root / "data/processed/live/industry_exposure_panel.csv",
        metadata={"source_files": source_files},
    )
    write_dataframe_with_metadata(
        build_analytical_data_dictionary(
            "data/processed/live/industry_exposure_panel.csv",
            exposures,
        ),
        root / "results/live/industry_exposure_panel_data_dictionary.csv",
        metadata={
            "source_files": ["data/processed/live/industry_exposure_panel.csv"],
            "stage": "industry_exposure_panel_data_dictionary",
        },
    )
    write_dataframe_with_metadata(
        composition,
        root / "results/live/industry_group_composition.csv",
        metadata={"source_files": source_files},
    )
    write_dataframe_with_metadata(
        growth,
        root / "results/live/industry_export_growth_decomposition.csv",
        metadata={"source_files": source_files},
    )
    write_dataframe_with_metadata(
        coverage,
        root / "results/diagnostics/industry_exposure/industry_exposure_coverage.csv",
        metadata={"source_files": source_files},
    )
    write_dataframe_with_metadata(
        status,
        root / "results/diagnostics/industry_exposure/industry_exposure_status.csv",
        metadata={
            "source_files": [
                "data/processed/live/industry_exposure_panel.csv",
                "results/live/industry_group_composition.csv",
                "results/live/industry_export_growth_decomposition.csv",
            ]
        },
    )
    write_text_lf(root / "results/live/industry_exposure_diagnostics.txt", notes)


def build_descriptive_results(settings: Settings) -> None:
    """Build stable descriptive trade-orientation tables."""

    root = settings.resolved_root()
    results = build_descriptive_trade_results(root)
    classification_registry = root / "config/partner_groups.yml"
    source_files = ["data/interim/live/comtrade_coverage_matrix.csv"]
    if (root / "config/historical_groups.yml").exists() and (
        root / "config/comtrade_partner_areas.yml"
    ).exists():
        source_files.extend(["config/historical_groups.yml", "config/comtrade_partner_areas.yml"])
        classification_registry = root / "config/historical_groups.yml"
    else:
        source_files.append("config/partner_groups.yml")
    output_map = {
        "preliminary_group_shares": root / "results/live/preliminary_trade_group_shares.csv",
        "preliminary_colonial_share": root / "results/live/preliminary_colonial_share.csv",
        "diagnostic_selected_group_values": root
        / "results/diagnostics/comtrade_coverage/selected_group_values.csv",
        "diagnostic_selected_group_shares": root
        / "results/diagnostics/comtrade_coverage/selected_group_shares.csv",
        "diagnostic_period_changes": root
        / "results/diagnostics/comtrade_coverage/selected_group_changes_1962_1973.csv",
        "diagnostic_product_composition": root
        / "results/diagnostics/comtrade_coverage/selected_product_composition.csv",
        "diagnostic_concentration": root
        / "results/diagnostics/comtrade_coverage/selected_group_concentration.csv",
        "diagnostic_export_growth_contribution": root
        / "results/diagnostics/comtrade_coverage/selected_export_growth_contributions.csv",
        "diagnostic_missingness": root
        / "results/diagnostics/comtrade_coverage/source_quality_indicators.csv",
    }
    for key, path in output_map.items():
        write_dataframe_with_metadata(
            results[key],
            path,
            metadata={
                "source_files": [
                    *source_files,
                ],
                "classification_registry": classification_registry.relative_to(root).as_posix(),
                "classification_registry_sha256": sha256_file(classification_registry),
            },
        )
    notes = root / "results/live/preliminary_trade_notes.txt"
    write_text_lf(
        notes,
        "\n".join(
            [
                "Preliminary trade-orientation results",
                "=====================================",
                "",
                "The live preliminary tables use UN Comtrade World totals as the denominator.",
                "The residual row is labelled non_colonial_world only when colonial",
                "partner coverage is complete; otherwise it is an unassigned World residual.",
                "European and institutional group-share rows are withheld from live preliminary",
                "results until the Comtrade source-area crosswalk has been reviewed against",
                "returned partner-area metadata for every requested year and flow.",
                "Colonial partner coverage remains under territorial-definition review; missing",
                "historical Comtrade partner areas are not interpreted as zero trade.",
                "Coverage-derived selected-partner diagnostics are stored under",
                "results/diagnostics/comtrade_coverage and should not be cited as final",
                "analytical result tables.",
                "",
            ]
        ),
    )


def prepare_empirical_extension(settings: Settings) -> None:
    """Prepare empirical-design artefacts without fitting models."""

    root = settings.resolved_root()
    empirical_code = "src/portugal_external_growth/empirical.py"
    output_source_registry = load_sectoral_output_source_registry_or_empty(root)
    write_dataframe_with_metadata(
        output_source_registry,
        root / "data/raw/live/sectoral_output/source_registry.csv",
        metadata={
            "stage": "sectoral_output_source_registry_pending_historical_sources"
            if output_source_registry.empty
            else "sectoral_output_source_registry_preserved"
        },
    )
    output_source_transitions = load_sectoral_output_source_transition_registry_or_empty(root)
    write_dataframe_with_metadata(
        output_source_transitions,
        root / "results/diagnostics/sectoral_output/source_transition_registry.csv",
        metadata={
            "source_files": ["data/raw/live/sectoral_output/source_registry.csv"],
            "stage": "sectoral_output_source_transition_registry_pending_historical_sources"
            if output_source_transitions.empty
            else "sectoral_output_source_transition_registry_preserved",
        },
    )
    sectoral_output = load_sectoral_output_panel_or_empty(root)
    write_dataframe_with_metadata(
        sectoral_output,
        root / "data/processed/live/sectoral_output_panel.csv",
        metadata={
            "source_files": [
                "data/raw/live/sectoral_output/source_registry.csv",
                "results/diagnostics/sectoral_output/source_transition_registry.csv",
            ],
            "stage": "sectoral_output_panel_pending_source_grounded_empirical_data"
            if sectoral_output.empty
            else "sectoral_output_panel_preserved_from_existing_data",
        },
    )
    write_dataframe_with_metadata(
        build_analytical_data_dictionary(
            "data/processed/live/sectoral_output_panel.csv",
            sectoral_output,
        ),
        root / "results/live/sectoral_output_panel_data_dictionary.csv",
        metadata={
            "source_files": ["data/processed/live/sectoral_output_panel.csv"],
            "stage": "sectoral_output_panel_data_dictionary",
        },
    )
    design = load_empirical_design_matrix_or_empty(root)
    write_dataframe_with_metadata(
        design,
        root / "data/interim/live/empirical_design_matrix.csv",
        metadata={
            "stage": "empirical_design_pending_prerequisites"
            if design.empty
            else "empirical_design_preserved_from_existing_matrix"
        },
    )
    write_dataframe_with_metadata(
        build_analytical_data_dictionary(
            "data/interim/live/empirical_design_matrix.csv",
            design,
        ),
        root / "results/live/empirical_design_matrix_data_dictionary.csv",
        metadata={
            "source_files": ["data/interim/live/empirical_design_matrix.csv"],
            "stage": "empirical_design_matrix_data_dictionary",
        },
    )
    write_dataframe_with_metadata(
        build_model_specification_registry(root),
        root / "results/live/model_specification_registry.csv",
        metadata={"source_files": [empirical_code], "stage": "candidate_model_registry"},
    )
    audit = build_empirical_readiness_audit(root)
    write_dataframe_with_metadata(
        audit,
        root / "results/live/empirical_readiness_audit.csv",
        metadata={
            "source_files": [
                "data/processed/live/validated_annual_aggregate_external_orientation.csv",
                "results/live/comtrade_product_extraction_status.csv",
                "results/diagnostics/comtrade_product/product_coverage_diagnostics.csv",
                "results/diagnostics/product_industry_mapping/product_mapping_status.csv",
                "results/live/product_industry_mapping_documentation.txt",
                "config/product_industry_mapping.yml",
                "data/raw/live/sectoral_output/source_registry.csv",
                "results/diagnostics/sectoral_output/source_transition_registry.csv",
                "data/processed/live/sectoral_output_panel.csv",
                "data/processed/live/industry_trade_panel.csv",
                "results/diagnostics/industry_exposure/industry_exposure_coverage.csv",
            ],
            "stage": "empirical_readiness_audit",
        },
    )
    write_text_lf(
        root / "results/live/empirical_readiness_audit.txt",
        build_empirical_readiness_audit_notes(audit),
    )
    review_path = root / "results/live/identification_strategy_review.csv"
    if review_path.exists():
        identification_review = pd.read_csv(review_path)
    else:
        identification_review = empty_identification_strategy_review()
    write_dataframe_with_metadata(
        identification_review,
        review_path,
        metadata={"source_files": [empirical_code], "stage": "identification_strategy_review"},
    )
    write_dataframe_with_metadata(
        build_empirical_prerequisite_status(root),
        root / "results/live/empirical_prerequisite_status.csv",
        metadata={
            "source_files": [
                "results/live/empirical_readiness_audit.csv",
                "results/live/identification_strategy_review.csv",
            ],
            "stage": "empirical_readiness",
        },
    )
    write_dataframe_with_metadata(
        empty_diagnostics(),
        root / "results/live/empirical_diagnostics.csv",
        metadata={"source_files": [empirical_code], "stage": "diagnostics_not_fit"},
    )
    write_dataframe_with_metadata(
        empty_coefficients(),
        root / "results/live/empirical_coefficients.csv",
        metadata={"source_files": [empirical_code], "stage": "coefficients_not_estimated"},
    )
    coefficient_text = root / "results/live/empirical_coefficients.txt"
    write_text_lf(
        coefficient_text,
        "No coefficients estimated; empirical prerequisites are not satisfied.\n",
    )
    risk_notes = root / "results/live/empirical_assumptions_and_risks.txt"
    write_text_lf(risk_notes, build_empirical_risk_notes())


def build_efta_policy_dataset(settings: Settings) -> None:
    """Build guarded EFTA policy/tariff outputs without inferring rates."""

    root = settings.resolved_root()
    sources, policy, product_mapping, coverage, status, notes = build_efta_policy_outputs(root)
    source_files = ["config/data_sources.yml"]
    write_dataframe_with_metadata(
        sources,
        root / "data/raw/live/efta_policy/source_registry.csv",
        metadata={"source_files": source_files, "stage": "efta_policy_source_registry"},
    )
    write_dataframe_with_metadata(
        policy,
        root / "data/interim/live/efta_policy_dataset.csv",
        metadata={"source_files": source_files, "stage": "efta_policy_blocked_empty_dataset"},
    )
    write_dataframe_with_metadata(
        build_analytical_data_dictionary(
            "data/interim/live/efta_policy_dataset.csv",
            policy,
        ),
        root / "results/live/efta_policy_data_dictionary.csv",
        metadata={
            "source_files": ["data/interim/live/efta_policy_dataset.csv"],
            "stage": "efta_policy_data_dictionary",
        },
    )
    write_dataframe_with_metadata(
        product_mapping,
        root / "data/interim/live/efta_policy_product_mapping.csv",
        metadata={"source_files": source_files, "stage": "efta_policy_product_mapping"},
    )
    write_dataframe_with_metadata(
        coverage,
        root / "results/diagnostics/efta_policy/efta_policy_coverage.csv",
        metadata={"source_files": source_files},
    )
    write_dataframe_with_metadata(
        status,
        root / "results/diagnostics/efta_policy/efta_policy_status.csv",
        metadata={"source_files": ["results/diagnostics/efta_policy/efta_policy_coverage.csv"]},
    )
    write_text_lf(root / "results/live/efta_policy_readiness.txt", notes)


def freeze_research_data(
    settings: Settings,
    *,
    verification_evidence_path: Path | None = None,
    create_archive: bool = False,
) -> None:
    """Create final research-data freeze reports and tracked-file archive metadata."""

    root = settings.resolved_root()
    declaration, blockers, checklist, provenance, dictionaries, archive, evidence, notes = (
        build_research_data_freeze_outputs(
            root,
            verification_evidence_path=verification_evidence_path,
            create_archive=create_archive,
        )
    )
    release_dir = root / "results/releases/current"
    evidence_path = verification_evidence_path or release_dir / "verification_evidence.csv"
    write_dataframe_with_metadata(
        evidence,
        release_dir / "verification_evidence.csv",
        metadata={
            "source_files": [str(evidence_path)] if verification_evidence_path else [],
            "stage": "freeze_verification_evidence",
        },
    )
    write_dataframe_with_metadata(
        declaration,
        release_dir / "release_readiness_declaration.csv",
        metadata={
            "source_files": [
                "results/validation/research_readiness_report.csv",
                "results/live/empirical_readiness_audit.csv",
            ],
            "stage": "research_data_release_readiness_declaration",
        },
    )
    write_dataframe_with_metadata(
        blockers,
        release_dir / "freeze_blocking_reasons.csv",
        metadata={
            "source_files": [
                "results/validation/research_readiness_report.csv",
                str(evidence_path),
            ]
        },
    )
    write_dataframe_with_metadata(
        checklist,
        release_dir / "freeze_checklist.csv",
        metadata={"source_files": ["results/releases/current/freeze_blocking_reasons.csv"]},
    )
    write_dataframe_with_metadata(
        provenance,
        release_dir / "final_result_table_provenance.csv",
        metadata={"source_files": ["results/live"], "stage": "final_result_table_provenance"},
    )
    write_dataframe_with_metadata(
        dictionaries,
        release_dir / "data_dictionary_coverage.csv",
        metadata={"source_files": ["data/processed/live", "data/interim/live"]},
    )
    write_dataframe_with_metadata(
        archive,
        release_dir / "release_archive_manifest.csv",
        metadata={"stage": "tracked_file_release_archive_manifest"},
    )
    write_dataframe_with_metadata(
        build_source_release_policy(root),
        release_dir / "source_release_policy.csv",
        metadata={
            "source_files": [
                "data/manual/source_documents/source_document_registry.csv",
                "data/manual/source_documents",
            ],
            "stage": "source_release_distribution_policy",
        },
    )
    write_text_lf(root / "RESEARCH_DATA_READINESS.txt", notes)
    write_text_lf(release_dir / "RESEARCH_DATA_READINESS.txt", notes)
    manifest = build_file_manifest(root)
    write_dataframe_with_metadata(
        manifest,
        root / "results/manifests/current_manifest.csv",
        metadata={"stage": "manifest", "scope": "current"},
    )


def refresh_sources(settings: Settings, *, overwrite: bool) -> None:
    """Refresh configured network sources and source-coverage snapshots."""

    extract_world_bank(settings, overwrite=overwrite)
    extract_comtrade(settings, overwrite=overwrite)
    audit_comtrade_coverage(settings, overwrite=overwrite)
    extract_bpstat(settings, overwrite=overwrite)


def run_diagnostics(settings: Settings) -> None:
    """Regenerate local diagnostic artefacts from committed inputs."""

    rebuild_comtrade_coverage_audit_from_local(settings)
    review_bpstat_registry(settings)
    prepare_ine_transcription(settings)
    reconcile_trade_sources(settings)
    build_validated_aggregate_orientation(settings)
    design_product_comtrade_extraction(settings)
    build_product_industry_mapping(settings)
    build_descriptive_industry_exposure(settings)
    build_sitc_industry_mapping(settings)
    build_descriptive_results(settings)
    prepare_empirical_extension(settings)
    build_efta_policy_dataset(settings)
    prepare_empirical_extension(settings)


def reproduce_from_local(settings: Settings) -> bool:
    """Regenerate every committed non-network intermediate and result artefact."""

    bootstrap(settings.resolved_root())
    build(settings)
    run_diagnostics(settings)
    return validate(settings)


def run_all_available(settings: Settings, *, overwrite: bool) -> bool:
    """Run every configured online and local workflow currently available."""

    refresh_sources(settings, overwrite=overwrite)
    build(settings)
    run_diagnostics(settings)
    return validate(settings)


def run_all(settings: Settings, *, overwrite: bool) -> bool:
    """Backward-compatible alias for the complete available workflow."""

    return run_all_available(settings, overwrite=overwrite)
