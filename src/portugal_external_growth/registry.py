"""Configuration registries for reviewed external data sources."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from portugal_external_growth.config import load_yaml

PROJECT_START_YEAR = 1960
PROJECT_END_YEAR = 1973
BPSTAT_REVIEW_STATUS_PREFIXES = ("accepted", "rejected", "held")

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
    invalid_rows: list[str] = []
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            raise TypeError("Each BPstat reviewed candidate must be a mapping")
        missing = REQUIRED_BPSTAT_REVIEW_FIELDS.difference(candidate)
        blank = sorted(
            field
            for field in REQUIRED_BPSTAT_REVIEW_FIELDS.intersection(candidate)
            if _is_blank(candidate[field])
        )
        if missing:
            missing_rows.append(f"row {index}: {sorted(missing)}")
        if blank:
            missing_rows.append(f"row {index}: blank values for {blank}")
        if not missing and not blank:
            invalid_rows.extend(_validate_bpstat_candidate_values(candidate, index))
    if missing_rows:
        raise ValueError("BPstat reviewed candidates are incomplete: " + "; ".join(missing_rows))
    if invalid_rows:
        raise ValueError("BPstat reviewed candidates are invalid: " + "; ".join(invalid_rows))

    frame = pd.DataFrame.from_records(candidates)
    duplicate_slugs = frame.loc[frame["slug"].duplicated(keep=False), "slug"].tolist()
    duplicate_ids = frame.loc[frame["series_id"].duplicated(keep=False), "series_id"].tolist()
    if duplicate_slugs:
        raise ValueError(f"Duplicate BPstat candidate slugs: {duplicate_slugs}")
    if duplicate_ids:
        raise ValueError(f"Duplicate BPstat candidate series IDs: {duplicate_ids}")
    frame = _add_project_period_coverage(frame)
    return frame.sort_values(["concept", "slug"]).reset_index(drop=True)


def build_bpstat_registry_review(frame: pd.DataFrame) -> str:
    """Create a concise text review for BPstat candidate selection."""

    accepted = frame.loc[frame["review_status"].str.startswith("accepted")]
    rejected = frame.loc[frame["review_status"].str.startswith("rejected")]
    held = frame.loc[~frame.index.isin(accepted.index.union(rejected.index))]
    coverage_counts = frame["project_period_coverage_status"].value_counts().to_dict()
    full_coverage = coverage_counts.get("covers_full_project_period", 0)
    partial_coverage = coverage_counts.get("partial_project_period_overlap", 0)
    no_coverage = coverage_counts.get("outside_project_period", 0)
    candidate_lines = [
        (
            f"- {row['slug']}: {row['review_status']}; "
            f"{row['project_period_coverage_status']}; "
            f"{row['first_observation']} to {row['last_observation']}; "
            f"{row['rejection_or_hold_reason']}"
        )
        for row in frame.sort_values(["concept", "slug"]).to_dict(orient="records")
    ]
    return "\n".join(
        [
            "BPstat historical series registry review",
            "========================================",
            "",
            f"Reviewed candidates: {len(frame)}",
            f"Accepted for context only: {len(accepted)}",
            f"Rejected for 1960-1973 use: {len(rejected)}",
            f"Held for further review: {len(held)}",
            f"Full project-period coverage: {full_coverage}",
            f"Partial project-period coverage: {partial_coverage}",
            f"No project-period overlap: {no_coverage}",
            "",
            "No BPstat extraction series is enabled until territorial definitions,",
            "methodological breaks, and historical coverage are fully accepted.",
            "",
            "Candidate details:",
            *candidate_lines,
            "",
        ]
    )


def _is_blank(value: object) -> bool:
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _validate_bpstat_candidate_values(candidate: dict[object, object], index: int) -> list[str]:
    errors: list[str] = []
    errors.extend(_validate_positive_int(candidate["series_id"], "series_id", index))
    errors.extend(_validate_positive_int(candidate["domain_id"], "domain_id", index))

    first = _parse_observation_date(candidate["first_observation"], "first_observation", index)
    last = _parse_observation_date(candidate["last_observation"], "last_observation", index)
    if isinstance(first, str):
        errors.append(first)
    if isinstance(last, str):
        errors.append(last)
    if isinstance(first, pd.Timestamp) and isinstance(last, pd.Timestamp):
        if first > last:
            errors.append(f"row {index}: first_observation is after last_observation")
        status = _project_period_coverage_status(first, last)
        review_status = str(candidate["review_status"]).strip()
        if review_status.startswith("accepted") and status == "outside_project_period":
            errors.append(f"row {index}: accepted candidate has no 1960-1973 overlap")

    review_status = str(candidate["review_status"]).strip()
    if not review_status.startswith(BPSTAT_REVIEW_STATUS_PREFIXES):
        errors.append(
            "row "
            f"{index}: review_status must start with one of "
            f"{list(BPSTAT_REVIEW_STATUS_PREFIXES)}"
        )
    return errors


def _validate_positive_int(value: object, field: str, index: int) -> list[str]:
    if isinstance(value, bool):
        return [f"row {index}: {field} must be a positive integer"]
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return [f"row {index}: {field} must be a positive integer"]
    else:
        return [f"row {index}: {field} must be a positive integer"]
    if parsed <= 0:
        return [f"row {index}: {field} must be a positive integer"]
    return []


def _parse_observation_date(value: object, field: str, index: int) -> pd.Timestamp | str:
    if not isinstance(value, str | int | float):
        return f"row {index}: {field} must be a valid date"
    try:
        timestamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return f"row {index}: {field} must be a valid date"
    if pd.isna(timestamp):
        return f"row {index}: {field} must be a valid date"
    return timestamp


def _add_project_period_coverage(frame: pd.DataFrame) -> pd.DataFrame:
    enriched = frame.copy()
    overlap_start_years: list[int | None] = []
    overlap_end_years: list[int | None] = []
    coverage_statuses: list[str] = []
    for row in enriched.to_dict(orient="records"):
        first = pd.Timestamp(row["first_observation"])
        last = pd.Timestamp(row["last_observation"])
        coverage_status = _project_period_coverage_status(first, last)
        coverage_statuses.append(coverage_status)
        if coverage_status == "outside_project_period":
            overlap_start_years.append(None)
            overlap_end_years.append(None)
        else:
            overlap_start_years.append(max(first.year, PROJECT_START_YEAR))
            overlap_end_years.append(min(last.year, PROJECT_END_YEAR))
    enriched["project_period_coverage_status"] = coverage_statuses
    enriched["project_period_overlap_start_year"] = pd.Series(overlap_start_years, dtype="Int64")
    enriched["project_period_overlap_end_year"] = pd.Series(overlap_end_years, dtype="Int64")
    return enriched


def _project_period_coverage_status(first: pd.Timestamp, last: pd.Timestamp) -> str:
    if last.year < PROJECT_START_YEAR or first.year > PROJECT_END_YEAR:
        return "outside_project_period"
    if first.year <= PROJECT_START_YEAR and last.year >= PROJECT_END_YEAR:
        return "covers_full_project_period"
    return "partial_project_period_overlap"
