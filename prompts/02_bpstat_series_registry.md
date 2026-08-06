# Prompt 02 — BPstat Historical Series Registry

Build a reviewed BPstat series registry for Portugal, 1960–1973.

## Candidate concepts

- real GDP and GDP growth;
- GDP deflator;
- exports and imports of goods and services;
- gross fixed capital formation;
- manufacturing value added or industrial production;
- employment and population;
- current account, remittances, tourism, and investment income where historical coverage exists.

## Required checks for every series

- exact series identifier;
- domain and dataset identifiers;
- frequency;
- units and price basis;
- first and last observation;
- territorial definition: mainland, metropolitan Portugal, present territory, or another scope;
- reconstruction method and methodological breaks;
- whether the series is original, reconstructed, or harmonised.

## Deliverables

- populated `config/bpstat_series.yml`;
- `data/interim/live/bpstat_series_registry.csv`;
- `results/live/bpstat_registry_review.txt`;
- tests ensuring unique slugs and series identifiers.

Do not choose a series merely because its label contains GDP. Territorial and accounting definitions are mandatory.
