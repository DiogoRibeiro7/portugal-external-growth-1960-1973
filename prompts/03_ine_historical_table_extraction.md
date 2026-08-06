# Prompt 03 — INE Historical Trade Table Extraction

Implement a controlled workflow to transcribe historical INE trade tables that are unavailable as structured data.

## Rules

- Use the existing transcription template.
- Preserve the original table title, page, units, currency, commodity label, partner label, and footnotes.
- Use two independent entry passes for every table.
- Never correct a historical label in the raw transcription. Add harmonised codes in separate columns.
- Store the source PDF filename and SHA-256 hash.
- Compare extracted totals with the publication's printed totals.
- Flag unreadable cells rather than guessing.

## Deliverables

- source-document registry;
- two independent transcription CSVs;
- discrepancy report;
- adjudicated intermediate CSV;
- final harmonised CSV;
- TXT report listing all unresolved cells and footnotes.

No OCR-only value may become final without human verification.
