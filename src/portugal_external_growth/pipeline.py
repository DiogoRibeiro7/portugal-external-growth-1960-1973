"""End-to-end extraction, transformation, and validation orchestration."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.clients.bpstat import BPstatClient, BPstatSeries
from portugal_external_growth.clients.comtrade import ComtradeClient, ComtradeRequest
from portugal_external_growth.clients.world_bank import WorldBankClient, WorldBankRequest
from portugal_external_growth.config import load_yaml
from portugal_external_growth.http import build_session
from portugal_external_growth.io_utils import write_dataframe_with_metadata
from portugal_external_growth.manual import initialise_templates, prepare_ine_transcription_workflow
from portugal_external_growth.reconciliation import (
    build_trade_reconciliation_notes,
    build_trade_source_comparison,
    finalise_trade_reconciliation,
)
from portugal_external_growth.registry import (
    build_bpstat_registry_review,
    load_bpstat_reviewed_candidates,
)
from portugal_external_growth.settings import Settings
from portugal_external_growth.transforms import (
    aggregate_trade_orientation,
    classify_partner_groups,
    compile_comtrade_coverage_audit,
    load_partner_memberships,
    normalise_comtrade,
    summarise_gdp_growth,
)
from portugal_external_growth.validation import (
    ValidationIssue,
    build_file_manifest,
    issues_to_frame,
    validate_trade_shares,
    validate_unique,
    validate_year_range,
)


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
    manifest = build_file_manifest(root)
    write_dataframe_with_metadata(
        manifest,
        root / "results/manifests/bootstrap_manifest.csv",
        metadata={"stage": "manifest", "scope": "bootstrap"},
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
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


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
        raw, frame, url = client.fetch(request)
        client.save(request, raw, frame, url, root, overwrite=overwrite)


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
    partners = tuple(int(value) for value in config["partner_codes"])
    for year in config["years"]:
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
            raw, frame, url = client.fetch(request)
            client.save(request, raw, frame, url, root, overwrite=overwrite)


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
    years = tuple(int(year) for year in config["years"])
    flows = tuple(str(flow_code) for flow_code in config["flow_codes"])
    partners = tuple(int(value) for value in config["partner_codes"])

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
                raw, frame, url = client.fetch(request)
                raw_path = client.save_availability_response(
                    request,
                    raw,
                    frame,
                    url,
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
                                    "trade_value_usd": pd.NA,
                                    "is_world_record": False,
                                    "raw_records": 0,
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
                        "partner_desc": frame.get("partnerDesc", pd.Series([""] * len(frame))),
                        "trade_value_usd": normalised["trade_value_usd"],
                        "is_world_record": normalised["partner_code"].eq(0),
                        "raw_records": len(frame),
                    }
                )
                matrix_inputs.append(matrix)

    coverage_matrix, audit, notes = compile_comtrade_coverage_audit(
        matrix_inputs,
        colonial_partner_codes=tuple(partners[1:8]),
        expected_years=years,
        expected_flow_codes=flows,
    )
    write_dataframe_with_metadata(
        coverage_matrix,
        root / "data/interim/live/comtrade_coverage_matrix.csv",
        metadata={"source_files": raw_paths, "stage": "comtrade_coverage_matrix"},
    )
    write_dataframe_with_metadata(
        audit,
        root / "results/live/comtrade_coverage_audit.csv",
        metadata={"source_files": ["data/interim/live/comtrade_coverage_matrix.csv"]},
    )
    notes_path = root / "results/live/comtrade_coverage_notes.txt"
    notes_path.parent.mkdir(parents=True, exist_ok=True)
    notes_path.write_text(notes, encoding="utf-8")


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
    grouped: dict[tuple[int, str], list[int]] = {}
    for item in metadata:
        domain_ids = item.get("domain_ids")
        dataset_id = item.get("dataset_id")
        series_id = item.get("id") or item.get("series_id")
        if not isinstance(domain_ids, list) or not domain_ids:
            raise ValueError("BPstat metadata is missing domain_ids")
        if not isinstance(dataset_id, str) or not isinstance(series_id, int):
            raise ValueError("BPstat metadata is missing dataset_id or series identifier")
        grouped.setdefault((int(domain_ids[0]), dataset_id), []).append(series_id)
    for (domain_id, dataset_id), grouped_ids in grouped.items():
        series_ids = tuple(grouped_ids)
        raw, frame, url = client.fetch_dataset(
            domain_id=domain_id, dataset_id=dataset_id, series_ids=series_ids
        )
        client.save(
            raw_json=raw,
            frame=frame,
            request_url=url,
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
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")


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
        memberships = load_partner_memberships(root / "config/partner_groups.yml")
        classified = classify_partner_groups(normalised, memberships)
        write_dataframe_with_metadata(
            classified,
            root / "data/interim/live/comtrade_classified.csv",
            metadata={"source_files": ["data/interim/live/comtrade_normalised.csv"]},
        )
        orientation = aggregate_trade_orientation(classified)
        write_dataframe_with_metadata(
            orientation,
            root / "data/processed/live/trade_orientation_by_group.csv",
            metadata={"source_files": ["data/interim/live/comtrade_classified.csv"]},
        )
        write_dataframe_with_metadata(
            orientation,
            root / "results/live/trade_orientation_by_group.csv",
            metadata={"result_type": "primary_trade_orientation"},
        )


def validate(settings: Settings) -> None:
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
    orientation_path = root / "data/processed/live/trade_orientation_by_group.csv"
    if orientation_path.exists():
        orientation = pd.read_csv(orientation_path)
        issues += validate_trade_shares(orientation)
    else:
        issues.append(
            ValidationIssue(
                "warning",
                "trade.available",
                "No live trade orientation table exists; run extract-comtrade and build.",
            )
        )
    write_dataframe_with_metadata(
        issues_to_frame(issues),
        root / "results/live/validation_report.csv",
        metadata={"stage": "validation"},
    )
    manifest = build_file_manifest(root)
    write_dataframe_with_metadata(
        manifest,
        root / "results/manifests/current_manifest.csv",
        metadata={"stage": "manifest", "scope": "current"},
    )


def init_manual_templates(root: Path) -> None:
    """Initialise transcription templates and print created paths."""

    for path in initialise_templates(root):
        print(path)


def prepare_ine_transcription(settings: Settings) -> None:
    """Initialise the controlled INE historical-table transcription workflow."""

    for path in prepare_ine_transcription_workflow(settings.resolved_root()):
        print(path)


def reconcile_trade_sources(settings: Settings) -> None:
    """Reconcile annual trade totals without silently merging conflicts."""

    root = settings.resolved_root()
    comparison = build_trade_source_comparison(root)
    write_dataframe_with_metadata(
        comparison,
        root / "data/interim/live/trade_source_comparison.csv",
        metadata={
            "source_files": [
                "results/live/comtrade_coverage_audit.csv",
                "data/processed/live/ine_trade_harmonised.csv",
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
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(notes, encoding="utf-8")


def run_all(settings: Settings, *, overwrite: bool) -> None:
    """Run all extractors that have sufficient configuration, then build and validate."""

    extract_world_bank(settings, overwrite=overwrite)
    extract_comtrade(settings, overwrite=overwrite)
    extract_bpstat(settings, overwrite=overwrite)
    build(settings)
    validate(settings)
