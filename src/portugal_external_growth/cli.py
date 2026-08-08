"""Command-line interface."""

from __future__ import annotations

import typer

from portugal_external_growth.pipeline import (
    audit_comtrade_coverage,
    bootstrap,
    build,
    build_bpstat_macro,
    build_descriptive_industry_exposure,
    build_descriptive_results,
    build_efta_policy_dataset,
    build_ine_harmonised_outputs,
    build_product_industry_mapping,
    build_sitc_industry_mapping,
    build_validated_aggregate_orientation,
    compare_ine_transcription_passes,
    design_product_comtrade_extraction,
    extract_bpstat,
    extract_comtrade,
    extract_comtrade_products,
    extract_world_bank,
    init_ine_transcription_inputs,
    init_manual_templates,
    prepare_empirical_extension,
    prepare_ine_transcription,
    reconcile_trade_sources,
    refresh_sources,
    reproduce_from_local,
    review_bpstat_registry,
    run_all,
    run_all_available,
    run_diagnostics,
    validate,
)
from portugal_external_growth.settings import Settings

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)


def _settings() -> Settings:
    settings = Settings()
    settings.validate_year_range()
    return settings


@app.command("bootstrap")
def bootstrap_command() -> None:
    """Rebuild deterministic local outputs without network access."""

    settings = _settings()
    bootstrap(settings.resolved_root())


@app.command("extract-world-bank")
def extract_world_bank_command(
    overwrite: bool = typer.Option(False, help="Replace existing raw snapshots."),
) -> None:
    """Download configured World Bank indicators."""

    extract_world_bank(_settings(), overwrite=overwrite)


@app.command("extract-comtrade")
def extract_comtrade_command(
    overwrite: bool = typer.Option(False, help="Replace existing raw snapshots."),
) -> None:
    """Download bounded UN Comtrade requests."""

    extract_comtrade(_settings(), overwrite=overwrite)


@app.command("extract-comtrade-products")
def extract_comtrade_products_command(
    overwrite: bool = typer.Option(False, help="Replace existing product raw snapshots."),
) -> None:
    """Download guarded subscription-key UN Comtrade product requests."""

    extract_comtrade_products(_settings(), overwrite=overwrite)


@app.command("audit-comtrade-coverage")
def audit_comtrade_coverage_command(
    overwrite: bool = typer.Option(False, help="Replace existing coverage-audit snapshots."),
) -> None:
    """Audit Portugal's historical UN Comtrade coverage."""

    audit_comtrade_coverage(_settings(), overwrite=overwrite)


@app.command("extract-bpstat")
def extract_bpstat_command(
    overwrite: bool = typer.Option(False, help="Replace existing raw snapshots."),
) -> None:
    """Download reviewed BPstat series."""

    extract_bpstat(_settings(), overwrite=overwrite)


@app.command("review-bpstat-registry")
def review_bpstat_registry_command() -> None:
    """Write the reviewed BPstat candidate registry."""

    review_bpstat_registry(_settings())


@app.command("init-manual-templates")
def init_manual_templates_command() -> None:
    """Create CSV templates for double-entry historical table transcription."""

    init_manual_templates(_settings().resolved_root())


@app.command("prepare-ine-transcription")
def prepare_ine_transcription_command() -> None:
    """Create controlled files for INE double-entry transcription."""

    prepare_ine_transcription(_settings())


@app.command("init-ine-transcription")
def init_ine_transcription_command() -> None:
    """Create protected INE double-entry transcription inputs."""

    init_ine_transcription_inputs(_settings())


@app.command("compare-ine-transcriptions")
def compare_ine_transcriptions_command() -> None:
    """Regenerate INE double-entry discrepancy outputs."""

    compare_ine_transcription_passes(_settings())


@app.command("build-ine-harmonised")
def build_ine_harmonised_command() -> None:
    """Regenerate INE harmonisation placeholders pending adjudication."""

    build_ine_harmonised_outputs(_settings())


@app.command("reconcile-trade-sources")
def reconcile_trade_sources_command() -> None:
    """Write source-preserving trade reconciliation tables."""

    reconcile_trade_sources(_settings())


@app.command("build-sitc-industry-mapping")
def build_sitc_industry_mapping_command() -> None:
    """Build product-to-industry mapping outputs."""

    build_sitc_industry_mapping(_settings())


@app.command("build-product-industry-mapping")
def build_product_industry_mapping_command() -> None:
    """Build guarded product-to-industry mapping outputs."""

    build_product_industry_mapping(_settings())


@app.command("build-descriptive-results")
def build_descriptive_results_command() -> None:
    """Build descriptive trade-orientation result tables."""

    build_descriptive_results(_settings())


@app.command("build-descriptive-industry-exposure")
def build_descriptive_industry_exposure_command() -> None:
    """Build guarded descriptive industry-exposure outputs."""

    build_descriptive_industry_exposure(_settings())


@app.command("build-bpstat-macro")
def build_bpstat_macro_command() -> None:
    """Build BPstat macro and broad-sector context outputs."""

    build_bpstat_macro(_settings())


@app.command("design-product-comtrade-extraction")
def design_product_comtrade_extraction_command() -> None:
    """Build guarded product-level Comtrade extraction design outputs."""

    design_product_comtrade_extraction(_settings())


@app.command("build-validated-aggregate-orientation")
def build_validated_aggregate_orientation_command() -> None:
    """Build validated annual aggregate external-orientation outputs."""

    build_validated_aggregate_orientation(_settings())


@app.command("prepare-empirical-extension")
def prepare_empirical_extension_command() -> None:
    """Prepare empirical design artefacts without fitting models."""

    prepare_empirical_extension(_settings())


@app.command("build-efta-policy-dataset")
def build_efta_policy_dataset_command() -> None:
    """Build guarded EFTA policy and tariff dataset outputs."""

    build_efta_policy_dataset(_settings())


@app.command("build")
def build_command() -> None:
    """Transform all source files currently present locally."""

    build(_settings())


@app.command("validate")
def validate_command() -> None:
    """Run data contracts and write persistent reports."""

    if not validate(_settings()):
        raise typer.Exit(1)


@app.command("refresh-sources")
def refresh_sources_command(
    overwrite: bool = typer.Option(False, help="Replace existing raw snapshots."),
) -> None:
    """Refresh configured network sources and source coverage snapshots."""

    refresh_sources(_settings(), overwrite=overwrite)


@app.command("reproduce-from-local")
def reproduce_from_local_command() -> None:
    """Regenerate committed non-network outputs from local files."""

    if not reproduce_from_local(_settings()):
        raise typer.Exit(1)


@app.command("run-diagnostics")
def run_diagnostics_command() -> None:
    """Regenerate local diagnostics and readiness artefacts."""

    run_diagnostics(_settings())


@app.command("run-all-available")
def run_all_available_command(
    overwrite: bool = typer.Option(False, help="Replace existing raw snapshots."),
) -> None:
    """Run every configured online and local workflow currently available."""

    if not run_all_available(_settings(), overwrite=overwrite):
        raise typer.Exit(1)


@app.command("run-all")
def run_all_command(
    overwrite: bool = typer.Option(False, help="Replace existing raw snapshots."),
) -> None:
    """Extract, build, and validate all configured sources."""

    if not run_all(_settings(), overwrite=overwrite):
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
