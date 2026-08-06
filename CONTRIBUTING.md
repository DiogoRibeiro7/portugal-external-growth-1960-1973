# Contributing

This repository is a reproducible research pipeline. Contributions should preserve provenance, source traceability, and deterministic outputs.

## Development Setup

```bash
poetry install
cp .env.example .env
poetry run pre-commit install
```

## Checks

Run these before opening a pull request:

```bash
make quality
make test
```

Use `make bootstrap` when changes affect committed bootstrap data or generated bootstrap results.

## Data Rules

- Do not commit `.env` files, API keys, or live raw API payloads.
- Keep committed bootstrap data small and deterministic.
- Write sidecar metadata for any committed data table.
- Document source definitions and historical classification decisions in configuration or documentation.

## Pull Requests

Each pull request should explain:

- what changed;
- why the change is needed;
- whether outputs were regenerated;
- which checks were run.
