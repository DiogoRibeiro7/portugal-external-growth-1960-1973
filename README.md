# Portugal External Growth 1960–1973

Reproducible data repository for studying the relative importance of colonial and European economic linkages in Portuguese growth between 1960 and 1973.

This repository contains **data engineering and analytical code only**. It intentionally does not contain a paper, argument, narrative conclusion, or publication draft. Those should be written only after the data pipeline, territorial definitions, classifications, and cross-checks are stable.

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

Human-readable outputs are written to `results/`. Each run creates SHA-256 hashes, row counts, date ranges, and source metadata. Existing raw files are not overwritten unless `--overwrite` is explicitly supplied.

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

# Run the complete available pipeline
poetry run peg run-all
```

Equivalent Make targets are available:

```bash
make bootstrap
make extract
make build
make validate
make test
make quality
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
- input file hashes;
- output schema;
- row count and date range;
- validation warnings.

The `results/manifests/` directory is intended to be archived with any submitted paper version.

## Important historical definitions

Partner groups are time-aware. The project does not use current EU membership to classify historical trade. The default groups distinguish:

- Portuguese colonies and overseas territories;
- founding EFTA members and later associates/members during the sample;
- the six EEC members during 1960–1973;
- the rest of the world.

The classification registry must be reviewed against contemporary Portuguese statistical definitions, especially the treatment of the escudo area and overseas provinces.
