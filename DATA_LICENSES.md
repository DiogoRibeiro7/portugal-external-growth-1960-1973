# Data Licenses and Redistribution Policy

## Code

Repository code is licensed under the MIT License in `LICENSE`.

## Source Data

Downloaded and transcribed source data remain subject to the licence, terms, and
access conditions of their original providers. The MIT License for this
repository does not relicense third-party source data.

## Provider Policy

- UN Comtrade: use and redistribution are governed by UN Comtrade terms and
  re-dissemination policy. Raw API responses should only be committed when those
  terms allow redistribution for the intended release.
- World Bank: indicator data remain subject to World Bank data terms and source
  attribution requirements.
- Banco de Portugal BPstat: downloaded series remain subject to Banco de
  Portugal terms, licences, and citation requirements.
- INE historical publications: transcriptions and source-document excerpts
  remain subject to the licence and access conditions recorded for each source
  document.

## Release Rule

Before any public release, decide source by source whether to publish raw
responses, derived tables only, or retrieval metadata with checksums and source
citations. The release freeze writes
`results/releases/current/source_release_policy.csv` with that decision.

When redistribution rights are unresolved, or when a source carries a restrictive
notice, release archives must exclude the local source document and include only
metadata, checksums, citations, and derived tables until the source-specific
terms are resolved.
