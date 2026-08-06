"""Command-line interface."""

from __future__ import annotations

import typer

from portugal_external_growth.pipeline import (
    audit_comtrade_coverage,
    bootstrap,
    build,
    extract_bpstat,
    extract_comtrade,
    extract_world_bank,
    init_manual_templates,
    prepare_ine_transcription,
    reconcile_trade_sources,
    review_bpstat_registry,
    run_all,
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


@app.command("reconcile-trade-sources")
def reconcile_trade_sources_command() -> None:
    """Write source-preserving trade reconciliation tables."""

    reconcile_trade_sources(_settings())


@app.command("build")
def build_command() -> None:
    """Transform all source files currently present locally."""

    build(_settings())


@app.command("validate")
def validate_command() -> None:
    """Run data contracts and write persistent reports."""

    validate(_settings())


@app.command("run-all")
def run_all_command(
    overwrite: bool = typer.Option(False, help="Replace existing raw snapshots."),
) -> None:
    """Extract, build, and validate all configured sources."""

    run_all(_settings(), overwrite=overwrite)


if __name__ == "__main__":
    app()
