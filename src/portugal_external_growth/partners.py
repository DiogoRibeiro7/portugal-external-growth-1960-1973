"""Historical partner entities and source-specific trade-area mappings."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import cast

import pandas as pd

from portugal_external_growth.config import load_yaml

AREA_COLUMNS = [
    "entity_id",
    "entity_label",
    "m49_code",
    "comtrade_area_code",
    "comtrade_area_label",
    "start_year",
    "end_year",
    "mapping_status",
    "mapping_source",
]

MEMBERSHIP_COLUMNS = [
    "year",
    "partner_code",
    "partner_name",
    "partner_group",
    "entity_id",
    "historical_trade_area",
    "mapping_status",
    "mapping_source",
    "participation_status",
]


def load_comtrade_partner_areas(path: Path) -> pd.DataFrame:
    """Load source-specific Comtrade partner areas."""

    payload = load_yaml(path)
    records = payload.get("comtrade_partner_areas")
    if not isinstance(records, list):
        raise TypeError("comtrade_partner_areas.yml must contain a comtrade_partner_areas list")
    frame = pd.DataFrame.from_records(records, columns=AREA_COLUMNS)
    if frame.empty:
        return frame
    frame["comtrade_area_code"] = pd.to_numeric(frame["comtrade_area_code"], errors="raise").astype(
        "int64"
    )
    frame["start_year"] = pd.to_numeric(frame["start_year"], errors="raise").astype("int64")
    frame["end_year"] = pd.to_numeric(frame["end_year"], errors="raise").astype("int64")
    duplicates = frame.duplicated(["entity_id", "comtrade_area_code", "start_year"], keep=False)
    if duplicates.any():
        raise ValueError("Duplicate Comtrade partner-area mappings found")
    return frame.sort_values(["entity_id", "start_year", "comtrade_area_code"]).reset_index(
        drop=True
    )


def configured_comtrade_partner_codes(root: Path, years: tuple[int, ...]) -> tuple[int, ...]:
    """Return active Comtrade trade-area codes for configured extraction years."""

    area_path = root / "config/comtrade_partner_areas.yml"
    if not area_path.exists():
        payload = load_yaml(root / "config/comtrade.yml")
        config = payload.get("comtrade")
        if not isinstance(config, dict):
            raise TypeError("comtrade.yml is invalid")
        return tuple(int(value) for value in config["partner_codes"])
    areas = load_comtrade_partner_areas(area_path)
    active = areas.loc[
        areas.apply(
            lambda row: any(
                int(row["start_year"]) <= year <= int(row["end_year"]) for year in years
            ),
            axis=1,
        )
    ]
    return tuple(sorted(int(code) for code in active["comtrade_area_code"].unique().tolist()))


def load_historical_group_memberships(group_path: Path, area_path: Path) -> pd.DataFrame:
    """Expand conceptual group memberships to Comtrade trade-area-year memberships."""

    payload = load_yaml(group_path)
    groups = payload.get("groups")
    if not isinstance(groups, dict):
        raise TypeError("historical_groups.yml must contain a groups mapping")
    areas = load_comtrade_partner_areas(area_path)
    records: list[dict[str, object]] = []
    for group_name, members in groups.items():
        if not isinstance(members, list):
            continue
        for member in members:
            if not isinstance(member, dict):
                continue
            entity_id = str(member["entity_id"])
            start_year = int(member["start_year"])
            end_year = int(member["end_year"])
            entity_areas = areas.loc[areas["entity_id"].eq(entity_id)]
            for area in entity_areas.to_dict(orient="records"):
                active_start = max(start_year, int(area["start_year"]))
                active_end = min(end_year, int(area["end_year"]))
                if active_start > active_end:
                    continue
                for year in range(active_start, active_end + 1):
                    records.append(
                        {
                            "year": year,
                            "partner_code": int(area["comtrade_area_code"]),
                            "partner_name": str(area["entity_label"]),
                            "partner_group": str(group_name),
                            "entity_id": entity_id,
                            "historical_trade_area": str(area["comtrade_area_label"]),
                            "mapping_status": str(area["mapping_status"]),
                            "mapping_source": str(area["mapping_source"]),
                            "participation_status": str(member.get("participation_status", "")),
                        }
                    )
    if not records:
        return pd.DataFrame(columns=MEMBERSHIP_COLUMNS)
    return pd.DataFrame.from_records(records, columns=MEMBERSHIP_COLUMNS).drop_duplicates(
        ["year", "partner_code", "partner_group"]
    )


def annotate_comtrade_partner_areas(frame: pd.DataFrame, area_path: Path) -> pd.DataFrame:
    """Attach entity and mapping provenance to returned Comtrade partner codes."""

    if frame.empty:
        return frame
    areas = load_comtrade_partner_areas(area_path)
    lookup: dict[tuple[int, int], dict[str, object]] = {}
    for area in areas.to_dict(orient="records"):
        for year in range(int(area["start_year"]), int(area["end_year"]) + 1):
            lookup[(year, int(area["comtrade_area_code"]))] = cast(dict[str, object], area)
    output = frame.drop(
        columns=["entity_id", "historical_trade_area", "mapping_status", "mapping_source"],
        errors="ignore",
    ).copy()
    annotations: list[dict[str, object]] = []
    for row in output.to_dict(orient="records"):
        year = int(row["year"]) if pd.notna(row.get("year")) else 0
        code = int(row["partner_code"]) if pd.notna(row.get("partner_code")) else -1
        match = lookup.get((year, code), {})
        annotations.append(
            {
                "entity_id": match.get("entity_id", ""),
                "historical_trade_area": match.get("comtrade_area_label", ""),
                "mapping_status": match.get("mapping_status", "unmapped_returned_area"),
                "mapping_source": match.get("mapping_source", ""),
            }
        )
    return pd.concat([output.reset_index(drop=True), pd.DataFrame(annotations)], axis=1)


def build_requested_partner_return_status(
    coverage_matrix: pd.DataFrame,
    area_path: Path,
    *,
    years: tuple[int, ...],
    flows: tuple[str, ...],
    classification_codes: tuple[str, ...],
    configured_partner_codes: tuple[int, ...] | None = None,
    snapshot_partner_codes: dict[tuple[int, str, str], tuple[int, ...]] | None = None,
) -> pd.DataFrame:
    """Compare requested Comtrade areas with returned rows."""

    areas = load_comtrade_partner_areas(area_path)
    configured_codes = tuple(sorted(configured_partner_codes or areas["comtrade_area_code"]))
    configured_hash = partner_codes_sha256(configured_codes)
    rows: list[dict[str, object]] = []
    returned = coverage_matrix.loc[coverage_matrix["partner_code"].notna()].copy()
    returned_codes = {
        (
            int(row["year"]),
            str(row["flow_code"]),
            str(row["classification_code"]),
            int(row["partner_code"]),
        )
        for row in returned.to_dict(orient="records")
    }
    available = coverage_matrix.loc[
        coverage_matrix.get("trade_value_usd", pd.Series(dtype=object)).notna()
    ]
    available_classifications = {
        (int(row["year"]), str(row["flow_code"]), str(row["classification_code"]))
        for row in available.to_dict(orient="records")
    }
    available_reporters = {
        (int(row["year"]), str(row["flow_code"])) for row in available.to_dict(orient="records")
    }
    for year in years:
        active = areas.loc[(areas["start_year"] <= year) & (areas["end_year"] >= year)]
        for flow_code in flows:
            for classification_code in classification_codes:
                key = (year, flow_code, classification_code)
                snapshot_codes = (
                    tuple(sorted(snapshot_partner_codes[key]))
                    if snapshot_partner_codes and key in snapshot_partner_codes
                    else configured_codes
                )
                snapshot_hash = partner_codes_sha256(snapshot_codes)
                snapshot_status = (
                    "current_against_configuration"
                    if snapshot_codes == configured_codes
                    else "stale_against_current_configuration"
                )
                for area in active.to_dict(orient="records"):
                    code = int(area["comtrade_area_code"])
                    is_returned = (year, flow_code, classification_code, code) in returned_codes
                    was_requested = code in snapshot_codes
                    classification_available = key in available_classifications
                    reporter_available = (year, flow_code) in available_reporters
                    rows.append(
                        {
                            "year": year,
                            "flow_code": flow_code,
                            "classification_code": classification_code,
                            "entity_id": area["entity_id"],
                            "entity_label": area["entity_label"],
                            "requested_partner_code": code,
                            "historical_trade_area": area["comtrade_area_label"],
                            "returned": is_returned,
                            "snapshot_requested": was_requested,
                            "snapshot_partner_codes": ",".join(
                                str(value) for value in snapshot_codes
                            ),
                            "snapshot_partner_codes_sha256": snapshot_hash,
                            "configured_partner_codes_sha256": configured_hash,
                            "snapshot_status": snapshot_status,
                            "mapping_status": area["mapping_status"],
                            "mapping_source": area["mapping_source"],
                            "absence_scope": _absence_scope(
                                is_returned=is_returned,
                                was_requested=was_requested,
                                reporter_available=reporter_available,
                                classification_available=classification_available,
                            ),
                            "resolution": _return_resolution(is_returned, was_requested),
                        }
                    )
    return pd.DataFrame.from_records(rows)


def partner_codes_sha256(codes: tuple[int, ...]) -> str:
    """Return a stable digest for a Comtrade partner-code request set."""

    payload = ",".join(str(code) for code in sorted(codes)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _return_resolution(is_returned: bool, was_requested: bool) -> str:
    if is_returned:
        return "returned"
    if not was_requested:
        return "not_requested_in_source_snapshot"
    return "not_returned_by_api"


def _absence_scope(
    *,
    is_returned: bool,
    was_requested: bool,
    reporter_available: bool,
    classification_available: bool,
) -> str:
    if is_returned:
        return "returned"
    if not was_requested:
        return "stale_request"
    if not reporter_available:
        return "reporter_unavailable"
    if not classification_available:
        return "classification_unavailable"
    return "partner_not_returned"
