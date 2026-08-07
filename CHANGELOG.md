# Changelog

All notable changes to this project will be documented in this file.

The format follows Keep a Changelog conventions, and this project uses semantic versioning once releases begin.

## [Unreleased]

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
