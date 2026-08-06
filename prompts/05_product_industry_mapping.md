# Prompt 05 — Product-to-Industry Mapping

Create a transparent mapping from historical SITC product groups to Portuguese production sectors.

## Constraints

- Prefer official correspondence tables.
- Preserve one-to-many mappings and weights when unavoidable.
- Do not pretend a product code identifies domestic value added.
- Separate re-exports where the data allow it.
- Record the classification revision and every manual decision.

## Deliverables

- raw correspondence files;
- `data/interim/live/sitc_industry_mapping.csv`;
- unmapped-code report;
- mapping-coverage statistics by trade value;
- sensitivity tables using broad and narrow mappings;
- tests for weight sums and duplicate keys.
