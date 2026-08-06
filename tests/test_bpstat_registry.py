from __future__ import annotations

from pathlib import Path

import pytest

from portugal_external_growth.registry import load_bpstat_reviewed_candidates


def test_bpstat_registry_rejects_duplicate_slugs(tmp_path: Path) -> None:
    path = tmp_path / "bpstat.yml"
    path.write_text(
        """
reviewed_candidates:
  - slug: population
    series_id: 1
    concept: population
    label: A
    domain_id: 13
    dataset_id: dataset
    frequency: annual
    units: people
    price_basis: not_applicable
    first_observation: "1960-01-01"
    last_observation: "1973-01-01"
    territorial_definition: Portugal
    reconstruction_method: source
    methodological_breaks: none_reviewed
    source_status: original
    review_status: accepted
    rejection_or_hold_reason: none
  - slug: population
    series_id: 2
    concept: population
    label: B
    domain_id: 13
    dataset_id: dataset
    frequency: annual
    units: people
    price_basis: not_applicable
    first_observation: "1960-01-01"
    last_observation: "1973-01-01"
    territorial_definition: Portugal
    reconstruction_method: source
    methodological_breaks: none_reviewed
    source_status: original
    review_status: accepted
    rejection_or_hold_reason: none
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate BPstat candidate slugs"):
        load_bpstat_reviewed_candidates(path)


def test_bpstat_registry_rejects_duplicate_series_ids(tmp_path: Path) -> None:
    path = tmp_path / "bpstat.yml"
    path.write_text(
        """
reviewed_candidates:
  - slug: population
    series_id: 1
    concept: population
    label: A
    domain_id: 13
    dataset_id: dataset
    frequency: annual
    units: people
    price_basis: not_applicable
    first_observation: "1960-01-01"
    last_observation: "1973-01-01"
    territorial_definition: Portugal
    reconstruction_method: source
    methodological_breaks: none_reviewed
    source_status: original
    review_status: accepted
    rejection_or_hold_reason: none
  - slug: employment
    series_id: 1
    concept: employment
    label: B
    domain_id: 13
    dataset_id: dataset
    frequency: annual
    units: people
    price_basis: not_applicable
    first_observation: "1960-01-01"
    last_observation: "1973-01-01"
    territorial_definition: Portugal
    reconstruction_method: source
    methodological_breaks: none_reviewed
    source_status: original
    review_status: accepted
    rejection_or_hold_reason: none
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Duplicate BPstat candidate series IDs"):
        load_bpstat_reviewed_candidates(path)
