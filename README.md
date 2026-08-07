# Portugal External Growth 1960–1973

[![CI](https://github.com/DiogoRibeiro7/portugal-external-growth-1960-1973/actions/workflows/ci.yml/badge.svg)](https://github.com/DiogoRibeiro7/portugal-external-growth-1960-1973/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](pyproject.toml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Reproducible data repository for studying the relative importance of colonial and European economic linkages in Portuguese growth between 1960 and 1973.

This repository contains **data engineering and analytical code only**. It intentionally does not contain a paper, argument, narrative conclusion, or publication draft. Those should be written only after the data pipeline, territorial definitions, classifications, and cross-checks are stable.

## Project status

The project is in active research-pipeline development. The committed bootstrap snapshot is deterministic and suitable for local validation. Live extraction workflows require network access and, for some UN Comtrade requests, an optional subscription key.

## Repository layout

```text
config/                         Source registries and historical classifications
data/raw/bootstrap/             Small committed source snapshot for offline checks
data/interim/bootstrap/         Normalised bootstrap tables
data/processed/bootstrap/       Stable bootstrap analysis tables
data/manual/templates/          Manual transcription templates
results/bootstrap/              Bootstrap validation and cross-check outputs
results/manifests/              File manifests with checksums
src/portugal_external_growth/   Package source code
tests/                          Unit tests and source fixtures
```

## Research boundary

The repository is designed to construct evidence for questions such as:

- How did the destination of Portuguese exports shift between colonial, EFTA, EEC, and other markets?
- Which product groups were most dependent on colonial markets?
- How did aggregate openness, exports, imports, and GDP evolve during the period?
- Are UN Comtrade, Banco de Portugal, INE, OECD, EFTA, and CEPII aggregates mutually consistent?

It does **not** treat gross exports as GDP and does not estimate a complete net return from colonialism without the necessary fiscal, financial, military, and opportunity-cost data.

## Reproducibility policy

The pipeline uses three data layers:

1. `data/raw/` — immutable source snapshots and response metadata.
2. `data/interim/` — normalised tables, code mappings, and harmonised classifications.
3. `data/processed/` — stable analysis tables used to generate final result files.

Human-readable outputs are written to `results/`. Processed outputs write portable metadata sidecars with repository-relative paths, SHA-256 hashes, row counts, dtypes, available year ranges, and input artefact hashes when the inputs are present locally. Existing raw files are not overwritten unless `--overwrite` is explicitly supplied.

## Initial data sources

| Source | Purpose | Access mode |
|---|---|---|
| World Bank Indicators API v2 | Macro cross-checks from 1960 | Open API |
| UN Comtrade API | Bilateral trade by partner and product from 1962 where available | Preview API or free subscription key |
| BPstat Data API v1 | Portuguese historical macro and balance-of-payments series | Open API |
| CEPII TRADHIST | Aggregate bilateral trade cross-check | Open research dataset |
| INE Digital Library | Historical trade and statistical yearbooks | Open documents; transcription required |
| OECD and EFTA historical reports | Definitions, totals, policy chronology, and cross-checks | Open documents; extraction required |

Official documentation:

- BPstat: `https://bpstat.bportugal.pt/data/docs`
- UN Comtrade: `https://uncomtrade.org/docs/un-comtrade-api/`
- World Bank API: `https://datahelpdesk.worldbank.org/knowledgebase/articles/898581-api-basic-call-structures`
- CEPII TRADHIST: `https://www.cepii.fr/CEPII/en/bdd_modele/bdd_modele_item.asp?id=32`

## Bootstrap snapshot

The repository includes a small deterministic World Bank GDP-growth snapshot for Portugal, covering 1961–1973. Its only purpose is to make validation and build commands work without network access. Production work should refresh it from the official API and retain the old snapshot for comparison.

No synthetic colonial or European trade data are stored in the empirical data folders. Synthetic records exist only under `tests/fixtures/`.

## Requirements

- Python 3.11–3.13
- Poetry 1.8+
- Internet access for live extraction
- Optional UN Comtrade subscription key for requests beyond the preview limits

## Setup

```bash
poetry install
cp .env.example .env
poetry run pre-commit install
```

The package is installed as the `peg` command-line application.

## Main commands

```bash
# Rebuild deterministic bootstrap outputs
poetry run peg bootstrap

# Download World Bank macro indicators
poetry run peg extract-world-bank

# Download UN Comtrade records by year and flow
poetry run peg extract-comtrade

# Download configured BPstat series
poetry run peg extract-bpstat

# Create manual transcription templates for historical PDFs
poetry run peg init-manual-templates

# Transform all available raw data
poetry run peg build

# Validate contracts and cross-source consistency
poetry run peg validate

# Refresh network sources and raw availability snapshots
poetry run peg refresh-sources

# Reproduce committed non-network outputs from local files
poetry run peg reproduce-from-local

# Regenerate local diagnostics and readiness artefacts
poetry run peg run-diagnostics

# Run every configured online and local workflow currently available
poetry run peg run-all-available
```

Equivalent Make targets are available:

```bash
make bootstrap
make extract
make build
make validate
make reproduce
make run-diagnostics
make run-all-available
make test
make quality
```

## Quality gates

The repository is configured with:

- Ruff formatting and linting;
- strict mypy checks for `src/` and `tests/`;
- pytest with branch coverage;
- pre-commit hooks for formatting, linting, YAML/JSON checks, and large-file protection;
- GitHub Actions CI across Python 3.11, 3.12, and 3.13;
- Dependabot checks for GitHub Actions and Python dependencies.

Before changing generated outputs, run:

```bash
make bootstrap
make validate
make reproduce
make quality
make test
```

## Data stability and peer-review support

Every extraction writes:

- the raw response or downloaded file;
- a sidecar metadata JSON file;
- the request URL without secret keys;
- extraction timestamp in UTC;
- SHA-256 checksum;
- HTTP status and content type;
- source-specific parameters.

Every processed table writes:

- a CSV file;
- a metadata JSON file;
- repository-relative input file references;
- input file hashes for existing local inputs;
- output column names and pandas dtypes;
- row count and available year range;
- validation findings when supplied by the generating step;
- source licence and access-condition fields, using `not_specified` until a source registry supplies confirmed values.

`poetry run peg validate` writes two distinct reports:

- `results/validation/data_integrity_report.csv` for structural data checks. Error-severity findings make the command exit non-zero.
- `results/validation/research_readiness_report.csv` for empirical readiness. This report may be `not_ready` even when data-integrity checks pass.

The `results/manifests/` directory is intended to be archived with any submitted paper version.

## Important historical definitions

Partner groups are time-aware. The project does not use current EU membership to classify historical trade. The default groups distinguish:

- Portuguese colonies and overseas territories;
- founding EFTA members and later associates/members during the sample;
- the six founding EEC members and the 1973 enlargement members;
- a fixed EFTA/EEC analytical partner sample for selected diagnostics;
- the rest of the world.

The classification registry must be reviewed against contemporary Portuguese statistical definitions, especially the treatment of the escudo area and overseas provinces.
