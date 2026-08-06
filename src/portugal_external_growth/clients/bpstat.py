"""Banco de Portugal BPstat Data API client."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from portugal_external_growth.http import get_bytes
from portugal_external_growth.io_utils import (
    atomic_write_bytes,
    atomic_write_json,
    sha256_file,
    utc_now_iso,
)


@dataclass(frozen=True)
class BPstatSeries:
    """Configured BPstat series metadata."""

    series_id: int
    slug: str
    expected_start_year: int | None = None
    expected_frequency: str | None = None
    territorial_definition: str | None = None
    notes: str | None = None


class BPstatClient:
    """Discover metadata and download configured BPstat series."""

    def __init__(self, session: requests.Session, timeout_seconds: int = 60) -> None:
        self._session = session
        self._timeout_seconds = timeout_seconds
        self._base_url = "https://bpstat.bportugal.pt/data/v1"

    def fetch_series_metadata(self, series_ids: tuple[int, ...]) -> list[dict[str, Any]]:
        """Return metadata for one or more series identifiers."""

        response = get_bytes(
            self._session,
            f"{self._base_url}/series/",
            params={"lang": "EN", "series_ids": ",".join(map(str, series_ids))},
            timeout_seconds=self._timeout_seconds,
        )
        payload = response.json()
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise ValueError("Unexpected BPstat series metadata response")
        return payload

    def fetch_dataset(
        self,
        *,
        domain_id: int,
        dataset_id: str,
        series_ids: tuple[int, ...],
    ) -> tuple[bytes, pd.DataFrame, str, dict[str, object]]:
        """Download a JSON-stat dataset and flatten it to a table."""

        url = f"{self._base_url}/domains/{domain_id}/datasets/{dataset_id}"
        params: dict[str, str | int] = {
            "lang": "EN",
            "series_ids": ",".join(map(str, series_ids)),
        }
        response = get_bytes(
            self._session,
            url,
            params=params,
            timeout_seconds=self._timeout_seconds,
        )
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected BPstat dataset response")
        frame = flatten_jsonstat(payload)
        return (
            response.content,
            frame,
            response.url,
            _http_provenance(
                response,
                endpoint=url,
                query_parameters=params,
            ),
        )

    def save(
        self,
        *,
        raw_json: bytes,
        frame: pd.DataFrame,
        request_url: str,
        http_metadata: dict[str, object],
        series_ids: tuple[int, ...],
        root: Path,
        overwrite: bool,
    ) -> tuple[Path, Path]:
        """Save BPstat raw and tabular snapshots."""

        stem = "series_" + "_".join(map(str, series_ids))
        raw_path = root / "data/raw/live/bpstat" / f"{stem}.json"
        csv_path = root / "data/raw/live/bpstat" / f"{stem}.csv"
        atomic_write_bytes(raw_path, raw_json, overwrite=overwrite)
        atomic_write_bytes(
            csv_path,
            frame.to_csv(index=False, lineterminator="\n").encode(),
            overwrite=overwrite,
        )
        atomic_write_json(
            raw_path.with_suffix(".metadata.json"),
            {
                "source": "BPstat Data API v1",
                "request_url": request_url,
                "extracted_at_utc": utc_now_iso(),
                **http_metadata,
                "raw_sha256": sha256_file(raw_path),
                "csv_sha256": sha256_file(csv_path),
                "rows": len(frame),
                "series_ids": list(series_ids),
            },
            overwrite=overwrite,
        )
        return raw_path, csv_path


def flatten_jsonstat(payload: dict[str, Any]) -> pd.DataFrame:
    """Flatten a JSON-stat dataset returned by BPstat.

    The implementation supports dense list values and sparse dictionary values.
    Category labels are preserved where available.
    """

    dimension_ids = payload.get("id")
    sizes = payload.get("size")
    dimensions = payload.get("dimension")
    values = payload.get("value")
    if not isinstance(dimension_ids, list) or not isinstance(sizes, list):
        raise ValueError("JSON-stat payload is missing id or size")
    if not isinstance(dimensions, dict):
        raise ValueError("JSON-stat payload is missing dimension metadata")
    if len(dimension_ids) != len(sizes):
        raise ValueError("JSON-stat id and size arrays differ in length")

    ordered_codes: list[list[str]] = []
    label_maps: dict[str, dict[str, str]] = {}
    for dimension_id, expected_size in zip(dimension_ids, sizes, strict=True):
        meta = dimensions.get(dimension_id)
        if not isinstance(meta, dict):
            raise ValueError(f"Missing metadata for dimension {dimension_id}")
        category = meta.get("category")
        if not isinstance(category, dict):
            raise ValueError(f"Missing category metadata for dimension {dimension_id}")
        index = category.get("index")
        labels = category.get("label")
        if isinstance(index, dict):
            codes = [code for code, _ in sorted(index.items(), key=lambda item: int(item[1]))]
        elif isinstance(index, list):
            codes = [str(code) for code in index]
        else:
            raise ValueError(f"Unsupported category index for dimension {dimension_id}")
        if len(codes) != int(expected_size):
            raise ValueError(f"Unexpected category count for dimension {dimension_id}")
        ordered_codes.append(codes)
        label_maps[str(dimension_id)] = (
            {str(key): str(value) for key, value in labels.items()}
            if isinstance(labels, dict)
            else {}
        )

    combinations = list(product(*ordered_codes))
    records: list[dict[str, object]] = []
    for flat_index, combination in enumerate(combinations):
        if isinstance(values, list):
            value = values[flat_index] if flat_index < len(values) else None
        elif isinstance(values, dict):
            value = values.get(str(flat_index))
        else:
            value = None
        record: dict[str, object] = {"value": value}
        for dimension_id, code in zip(dimension_ids, combination, strict=True):
            key = str(dimension_id)
            record[key] = code
            record[f"{key}_label"] = label_maps[key].get(code, code)
        records.append(record)
    return pd.DataFrame.from_records(records)


def _http_provenance(
    response: Any,
    *,
    endpoint: str,
    query_parameters: dict[str, str | int],
) -> dict[str, object]:
    return {
        "endpoint": endpoint,
        "query_parameters": query_parameters,
        "http_status": response.status_code,
        "content_type": response.headers.get("Content-Type", ""),
        "etag": response.headers.get("ETag", ""),
        "last_modified": response.headers.get("Last-Modified", ""),
        "api_version": "BPstat Data API v1",
        "source_licence": "subject_to_banco_de_portugal_terms",
        "access_conditions": "public_api_or_provider_terms",
        "territorial_definition": "series_specific_bpstat_metadata",
        "units": "series_specific",
    }
