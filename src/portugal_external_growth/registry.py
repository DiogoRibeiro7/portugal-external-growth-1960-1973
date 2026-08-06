"""Configuration registries for reviewed external data sources."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.config import load_yaml

REQUIRED_BPSTAT_REVIEW_FIELDS = {
    "slug",
    "series_id",
    "concept",
    "label",
    "domain_id",
    "dataset_id",
    "frequency",
    "units",
    "price_basis",
    "first_observation",
    "last_observation",
    "territorial_definition",
    "reconstruction_method",
    "methodological_breaks",
    "source_status",
    "review_status",
    "rejection_or_hold_reason",
}


def load_bpstat_reviewed_candidates(path: Path) -> pd.DataFrame:
    """Load and validate reviewed BPstat candidate metadata."""

    payload = load_yaml(path)
    candidates = payload.get("reviewed_candidates")
    if not isinstance(candidates, list):
        raise TypeError("bpstat_series.yml must contain a reviewed_candidates list")

    missing_rows: list[str] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise TypeError("Each BPstat reviewed candidate must be a mapping")
        missing = REQUIRED_BPSTAT_REVIEW_FIELDS.difference(candidate)
        if missing:
            missing_rows.append(f"row {index}: {sorted(missing)}")
    if missing_rows:
        raise ValueError("BPstat reviewed candidates are incomplete: " + "; ".join(missing_rows))

    frame = pd.DataFrame.from_records(candidates)
    duplicate_slugs = frame.loc[frame["slug"].duplicated(keep=False), "slug"].tolist()
    duplicate_ids = frame.loc[frame["series_id"].duplicated(keep=False), "series_id"].tolist()
    if duplicate_slugs:
        raise ValueError(f"Duplicate BPstat candidate slugs: {duplicate_slugs}")
    if duplicate_ids:
        raise ValueError(f"Duplicate BPstat candidate series IDs: {duplicate_ids}")
    return frame.sort_values(["concept", "slug"]).reset_index(drop=True)


def build_bpstat_registry_review(frame: pd.DataFrame) -> str:
    """Create a concise text review for BPstat candidate selection."""

    accepted = frame.loc[frame["review_status"].str.startswith("accepted")]
    rejected = frame.loc[frame["review_status"].str.startswith("rejected")]
    held = frame.loc[~frame.index.isin(accepted.index.union(rejected.index))]
    return "\n".join(
        [
            "BPstat historical series registry review",
            "========================================",
            "",
            f"Reviewed candidates: {len(frame)}",
            f"Accepted for context only: {len(accepted)}",
            f"Rejected for 1960-1973 use: {len(rejected)}",
            f"Held for further review: {len(held)}",
            "",
            "No BPstat extraction series is enabled until territorial definitions,",
            "methodological breaks, and historical coverage are fully accepted.",
            "",
        ]
    )
