# Prompt 01 — UN Comtrade Historical Coverage Audit

Audit Portugal's UN Comtrade coverage for 1962–1973 before expanding the trade pipeline.

## Questions to answer with code and output tables

- Is Portugal available as reporter code 620 in every year?
- Which original or converted classification is available: SITC Rev.1, SITC Rev.2, or another code?
- Are Angola, Mozambique, Guinea-Bissau, Cabo Verde, Sao Tome and Principe, Macao, and Timor-Leste reported as separate partners?
- Are overseas territories absent because they were included in Portugal's statistical territory?
- Do reported exports to World equal the sum of partner records within an acceptable tolerance?
- Are imports valued CIF and exports FOB?

## Deliverables

- `data/raw/live/comtrade_availability/*.json`
- `data/interim/live/comtrade_coverage_matrix.csv`
- `results/live/comtrade_coverage_audit.csv`
- `results/live/comtrade_coverage_notes.txt`
- tests for missing years, duplicate keys, and classification changes

Do not proceed to causal modelling. Do not infer absence from an empty API response until metadata and historical reporting practices have been checked.
