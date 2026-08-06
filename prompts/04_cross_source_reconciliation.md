# Prompt 04 — Cross-Source Reconciliation

Reconcile annual Portuguese trade totals from UN Comtrade, INE, OECD, EFTA, and CEPII without silently merging conflicts.

## Required output structure

For each year, flow, source, and territorial definition, retain:

- source value;
- source unit and currency;
- nominal conversion method, if any;
- coverage definition;
- included partners;
- difference from the selected benchmark;
- absolute and percentage discrepancy;
- explanatory note;
- confidence status.

## Deliverables

- `data/interim/live/trade_source_comparison.csv`
- `results/live/trade_reconciliation.csv`
- `results/live/trade_reconciliation_notes.txt`

Use tolerances only for validation flags. Do not average conflicting historical totals.
