# Changelog

All notable changes to this project will be documented in this file.

The format follows Keep a Changelog conventions, and this project uses semantic versioning once releases begin.

## [Unreleased]

### Added

- Model readiness now depends on high-level empirical prerequisites before model-specific extras.
- Empirical panel sufficiency now checks sector-year grid coverage, minimum years per sector, and
  residual degrees of freedom.
- Empirical readiness now checks that sector-year observations are unique.
- Empirical readiness now includes a `dependent_variable_coverage` gate and a scaffolded
  `sectoral_output_panel.csv` outcome panel.
- Sectoral-output readiness now separately audits nominal-source, real-output, output-growth,
  deflator, source-provenance, and outcome-definition consistency coverage.
- Sectoral-output readiness now includes a source registry scaffold and explicit 1963-1973
  growth-sample coverage for log-change outcomes.
- Sectoral-output diagnostics now include a source-transition registry scaffold for reviewed
  cross-source level bridges.
- Reviewed sectoral output growth is now materialised as
  `data/processed/live/sectoral_output_growth_panel.csv` with current/lag source lineage.
- Pipeline metadata writes now preserve repository-relative provenance when run from a different
  current working directory.
- Empirical readiness now audits `sectoral_output_sector_year_uniqueness` so the upstream
  sectoral-output panel must resolve to one analytical level per sector-year.
- The 1960 INE yearbook (both volumes) is registered with checksums and metadata, and its
  Quadro III rows are transcribed by double entry: World and Ultramar totals, the eight
  overseas territories, and the ten benchmark European partners the volume prints. Austria is
  not printed separately in 1960, so the eleven-country benchmark is not observable for that
  year and no value is derived for it.
- Double-entry transcription of the eleven fixed European partner rows printed in every INE
  benchmark volume (1962, 1965, 1970, 1973), giving the first source-grounded constant-composition
  European trade series: fixed-sample export share 43.5%, 47.6%, 51.8% and 60.1%.
- The validated aggregate table now publishes `residual_destinations_*` values and shares, so
  colonial market, European benchmark and residual destinations partition the world total
  exactly and can be charted as three exhaustive groups.
- The aggregate cross-check notes now document the benchmark's membership, why Finland and
  Ireland are excluded, what the residual group still contains, and where component
  reconciliation residuals are reported.
- `results/diagnostics/ine_partner_component_reconciliation.csv` reconciles every transcribed
  partner block against the printed aggregate it belongs to, reporting residuals and sample
  completeness in machine-readable form.
- The validated aggregate table now publishes `fixed_europe_sample_id`,
  `fixed_europe_partner_count` and `fixed_europe_import_share`, so the constant-composition
  benchmark can never be read as a measure of total European trade.
- Double-entry transcription of the printed overseas-territory partner rows (Cabo Verde, Guine,
  S. Tome e Principe, Angola, Mocambique, India, Macau, Timor) for the four INE benchmark years,
  so the colonial aggregate can be audited against its own printed components.
- `config/historical_groups.yml` registers `efta_eec_fixed_partner_sample_ine_benchmark`, the
  operational fixed European sample, and the validated aggregate table now derives
  `fixed_europe_*` by summing those reviewed partner rows instead of requiring a pre-summed row.

### Fixed

- Candidate model readiness can no longer bypass the identification-strategy review, territorial
  consistency, or cross-source reconciliation gates.
- Empirical readiness now enforces the exact configured sample-year set for design matrices and
  industry panels.
- Fixed-effect observation and residual-degree gates now use the actual sector-year model-matrix
  rank instead of an approximate parameter-count formula.
- Pipeline metadata root detection now prefers project sentinels before generic path markers such
  as `data` or `results`.
- Sectoral-output and deflator readiness now require actual sector-year observations instead of
  BPstat dictionary flags.
- Annual trade coverage now requires non-null world trade values for each sample year-flow row.
- Dependent-variable readiness now requires reviewed `sectoral_output_growth` values linked back to
  `sectoral_output_panel.csv::output_growth`.
- Outcome provenance now requires `source_id` values to resolve against the sectoral-output source
  registry and classification-break statuses to use an empirically usable controlled vocabulary.
- Output-growth readiness now validates `output_growth` as a deterministic prior-year log change
  of reviewed real output, and export-growth coverage is derived from sectoral export levels.
- Sectoral-output source registries now enforce non-placeholder source metadata, valid retrieval
  dates, resolved licence statuses, parseable year scopes, unique `source_id` values, and
  panel-source year/classification compatibility.
- Output-growth readiness now blocks growth across incompatible source, unit, price-basis,
  classification, mapping, or real-output-method regimes unless a reviewed source transition is
  registered, and records current/lag source IDs for accepted growth observations.
- `real_output_method` now uses a controlled vocabulary.
- Candidate model readiness now checks outcome-specific joined designs, so export-growth models
  require export-growth sector-years to overlap the exposure panel.
- Sectoral export-growth readiness now uses only validated `world_total` industry-trade rows from
  one explicit mapping regime and rejects blocked or partial mapped trade rows.
- Source-transition readiness now permits only `no_adjustment_required` links until non-trivial
  level-link transformations are implemented.
- Local sectoral-output registry sources now require existing files with matching SHA-256 hashes.
- `deflated_nominal` real-output rows now validate `real_output` against nominal output and the
  documented deflator convention.
- Materialised sectoral output-growth lineage is now checked against recomputed source-panel
  lineage before it can satisfy empirical readiness.
- `file://` sectoral-output registry locations are treated as local paths and cannot bypass
  checksum verification.
- Model readiness now declares model-specific high-level prerequisites and required outcomes, so
  export-growth candidate models no longer inherit the sectoral-output prerequisite by default.
- Release blocker IDs no longer duplicate the `research_` prefix.
- Analytical dictionary coverage now uses dataset-column dictionaries for the BPstat-derived context
  tables and complete exposure-value units.
- The published `valuation_basis` and `territorial_definition` of a year no longer come from
  whichever transcribed row sorted first. They are taken from the World rows that define the
  published aggregate and are labelled per flow when the source wording differs, so an export
  figure is never described by the import valuation convention.
- An ambiguous aggregate row now reads as missing instead of resolving to an arbitrary match.
- Cross-source comparisons no longer convert every INE year with the 1962 IMF par value.
  Conversion now requires a rate registered for that same year, and years without one are
  reported as `blocked_pending_year_exchange_rate` instead of borrowing another year's rate.
- The 1962 INE-Comtrade reconciliation now selects INE rows by reference year instead of
  relying on row order, which became unsafe once later benchmark years were transcribed.
- The fixed European benchmark is always recomputed from its configured members; a pre-summed
  row of unverified composition can no longer silently replace the 11-country sample.
- Duplicated sector-year output levels no longer produce an ambiguous economic lag: such rows are
  excluded from the reviewed output panel and from derived output growth.
- Local sectoral-output registry sources must now be repository-relative paths inside the project
  root, so external or traversal paths can no longer make the repository empirically ready.
- `sectoral_output_growth_panel.csv` now has a dataset-level dictionary specification, restoring the
  release checklist item for analytical data dictionaries.

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
