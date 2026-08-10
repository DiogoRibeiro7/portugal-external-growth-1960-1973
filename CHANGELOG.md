# Changelog

All notable changes to this project will be documented in this file.

The format follows Keep a Changelog conventions, and this project uses semantic versioning once releases begin.

## [Unreleased]

### Added

- Model readiness now depends on high-level empirical prerequisites before model-specific extras.
- Empirical panel sufficiency now checks sector-year grid coverage, minimum years per sector, and
  residual degrees of freedom.
- Pipeline metadata writes now preserve repository-relative provenance when run from a different
  current working directory.

### Fixed

- Candidate model readiness can no longer bypass the identification-strategy review, territorial
  consistency, or cross-source reconciliation gates.

## [0.1.6] - 2026-08-09

### Added

- Release-readiness checks now include fixed European partner-sample and reconciliation-scope
  regressions.
- CSV sidecar self-consistency tests verify committed artifact hashes, row counts, and columns.

### Changed

- Empirical readiness distinguishes the 1960-1973 historical/macro scope from the current
  1962-1973 bilateral trade panel.
- Freeze reports and empirical readiness artifacts were regenerated for the stricter provenance and
  reconciliation gates.

### Fixed

- Fixed European completeness no longer accepts EFTA-only observations.
- Cross-source reconciliation readiness requires distinct INE-Comtrade, CEPII, EFTA, and OECD
  scopes instead of four resolved rows.
- Verification evidence notes are idempotent, preventing repeated stale-scope messages.
- The pass-2 INE aggregate transcription metadata now describes its own CSV and all four source
  years.

## [0.1.5] - 2026-08-09

### Added

- Machine-readable identification-strategy review scaffolding for empirical readiness.
- Regression coverage preventing 1962-only reconciliation diagnostics from populating later
  benchmark years.
- Regression coverage for fixed European partner sample rows, LF-normalized manifests, and
  data-dictionary adequacy gates.

### Changed

- Validated aggregate orientation now reads the multi-year INE aggregate file
  `ine_aggregate_trade_harmonised.csv`.
- `fixed_europe_*` variables now use explicit fixed-sample aggregate rows instead of summing
  contemporaneous EFTA and EEC group totals.
- Empirical prerequisite status is derived from the readiness audit and identification review when
  repository artifacts are available.
- Existing empirical design matrices are preserved when they contain the core design schema.
- Preliminary complete residual rows are labelled `non_colonial_world` rather than
  `true_rest_of_world`.

### Fixed

- UN Comtrade diagnostic values are selected by year and concept, preventing 1962 diagnostics from
  leaking into 1965, 1970, and 1973 rows.
- Empirical territorial consistency, cross-source reconciliation, and usable-industry gates now use
  non-trivial research-readiness denominators.
- Release data-dictionary checks now reject placeholder descriptions, schema mismatches, missing
  analytical-use/source documentation, and missing meaningful units.
- Manifest fingerprints normalize LF text endings so Windows CRLF working trees do not invalidate
  clean repository reproduction.

## [0.1.4] - 2026-08-09

### Added

- Verification evidence now records a tracked-content fingerprint so release checks can distinguish
  stale validation from report-only metadata updates.
- Final result-table provenance records hashed input artifacts for real source files only.
- Regression coverage for fixed empirical sample denominators and release archive packaging.

### Changed

- Empirical readiness checks use the fixed 1962-1973 year-flow denominator for aggregate trade,
  colonial partner, and European partner completeness.
- Release archives exclude restricted source documents and self-referential release metadata, keeping
  the generated package small enough for GitHub release assets.
- Metadata sidecar timestamps are preserved when regenerated outputs are unchanged.

### Fixed

- Dirty-worktree release archives are now marked `post_commit_archive_required` instead of publishing
  a stale `git archive HEAD` checksum.
- Macro controls must be explicitly reviewed for empirical use before they can satisfy empirical
  readiness gates.

## [0.1.3] - 2026-08-08

### Added

- Guarded UN Comtrade product-level extraction design and blocked extraction status.
- Guarded product-to-industry mapping, industry exposure, empirical-readiness audit, and EFTA
  policy/tariff readiness outputs.
- Final research-data freeze reports with a `NOT_READY` declaration and machine-readable blockers.

### Changed

- Release archives are ignored locally so large generated zip files are not committed to Git.

## [0.1.2] - 2026-08-07

### Added

- Official two-volume 1962 INE external-trade source scans and provenance sidecars.
- Historical-source audit outputs for the 1962 INE acquisition milestone.
- INE transcription status report now includes source-document, checksum, pass-entry,
  adjudication, unreadable-cell, and footnote counts.

### Fixed

- Manual source-document availability now verifies local files and SHA-256 checksums.
- Multi-volume manual source records require matching filename and checksum counts.

## [0.1.1] - 2026-08-07

### Fixed

- Incomplete World residual rows no longer populate complete-share columns.
- Release archives can be built from tracked Git files only.
- Zenodo metadata now distinguishes current source integrations from future supported sources.

## [0.1.0] - 2026-08-07

### Added

- Initial reproducible data pipeline for Portuguese external economic linkages, 1960-1973.
- Bootstrap World Bank GDP-growth snapshot and validation outputs.
- Source clients for World Bank, UN Comtrade, and BPstat.
- Historical Comtrade partner-area crosswalk for Portugal's colonial, EFTA, EEC, and fixed
  EFTA/EEC comparison groups.
- Comtrade coverage audit outputs with request hashes, returned-partner status, quality flags, and
  fresh snapshots using historical partner-area codes.
- Preliminary colonial-share outputs that distinguish observed lower bounds from complete
  partner-set estimates.
- Protected INE transcription and adjudication workflow under `data/manual/`.
- HTTP provenance metadata sidecars and data-licensing documentation.
- Research-readiness reports for empirical prerequisites, manual source availability,
  territorial-definition review, source reconciliation, and product mapping.
- Territorial-definition evidence registry for resolving Portugal reporter-territory status.
- LF-normalized text-output writer for cross-platform manifest stability.
- BPstat registry project-period coverage fields and per-candidate review details.

### Changed

- Comtrade coverage diagnostics now live under `results/diagnostics/comtrade_coverage/`.
- Missing requested partners distinguish stale requests, unavailable classifications, unavailable
  reporters, and partner-level absences.
- BPstat candidate review validation now rejects blank mandatory fields, invalid identifiers,
  invalid observation windows, and accepted candidates outside 1960-1973.
