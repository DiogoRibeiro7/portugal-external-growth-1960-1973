from __future__ import annotations

from pathlib import Path

import pytest

from portugal_external_growth.registry import (
    build_bpstat_registry_review,
    load_bpstat_reviewed_candidates,
)


def test_bpstat_registry_loads_sorted_complete_candidates(tmp_path: Path) -> None:
    path = tmp_path / "bpstat.yml"
    path.write_text(
        """
reviewed_candidates:
  - slug: z_population
    series_id: 2
    concept: population
    label: Z
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
    review_status: accepted_for_context
    rejection_or_hold_reason: none
  - slug: a_exports
    series_id: 1
    concept: exports
    label: A
    domain_id: 3
    dataset_id: dataset
    frequency: annual
    units: euros
    price_basis: current_prices
    first_observation: "1960-01-01"
    last_observation: "1973-01-01"
    territorial_definition: Portugal
    reconstruction_method: source
    methodological_breaks: none_reviewed
    source_status: original
    review_status: rejected_for_1960_1973
    rejection_or_hold_reason: not comparable
""",
        encoding="utf-8",
    )

    frame = load_bpstat_reviewed_candidates(path)
    report = build_bpstat_registry_review(frame)

    assert frame["slug"].tolist() == ["a_exports", "z_population"]
    assert "Reviewed candidates: 2" in report
    assert "Accepted for context only: 1" in report
    assert "Rejected for 1960-1973 use: 1" in report


def test_bpstat_registry_rejects_incomplete_candidates(tmp_path: Path) -> None:
    path = tmp_path / "bpstat.yml"
    path.write_text(
        """
reviewed_candidates:
  - slug: population
    series_id: 1
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="incomplete"):
        load_bpstat_reviewed_candidates(path)


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
