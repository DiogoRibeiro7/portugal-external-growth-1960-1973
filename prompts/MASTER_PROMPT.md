# Master Development Prompt

You are extending the `portugal-external-growth-1960-1973` repository.

## Non-negotiable rules

1. Do not write or edit an academic paper, abstract, introduction, conclusion, or political argument.
2. Work only on data acquisition, data contracts, provenance, transformations, validation, descriptive results, and transparent econometric preparation.
3. Preserve every raw source snapshot. Never overwrite raw data by default.
4. Write all code, comments, filenames, schemas, and documentation in English.
5. Use mathematically transparent methods. Do not introduce machine learning.
6. Every new source must include access conditions, licence, request parameters, extraction date, territorial definition, units, and SHA-256 hashes.
7. Every transformation must write an intermediate CSV before producing a final result table.
8. Every result must be reproducible from local raw files without another network request.
9. Add tests, type annotations, docstrings, validation checks, and explicit error handling.
10. Never silently reconcile conflicting values. Preserve both observations and write a cross-check table explaining the discrepancy.

## Required workflow

1. Inspect the existing repository and source registry.
2. State the exact bounded task.
3. Implement extraction or transformation code.
4. Add deterministic fixtures and unit tests.
5. Run formatting, linting, typing, tests, and the relevant pipeline command.
6. Write or update CSV/TXT cross-check outputs.
7. Update manifests and provenance.
8. Report unresolved data gaps without inventing values.

## Completion criteria

A task is complete only when:

- source files are local;
- intermediate files exist;
- processed files exist where applicable;
- cross-check results exist in CSV or TXT;
- provenance and checksums exist;
- tests pass;
- no paper prose was introduced.
