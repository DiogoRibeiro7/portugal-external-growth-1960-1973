"""World Bank Indicators API client."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import requests

from portugal_external_growth.http import get_bytes
from portugal_external_growth.io_utils import (
    atomic_write_bytes,
    atomic_write_json,
    sanitise_url,
    sha256_file,
    utc_now_iso,
)


@dataclass(frozen=True)
class WorldBankRequest:
    """Parameters for one World Bank indicator request."""

    country_code: str
    indicator_code: str
    start_year: int
    end_year: int


class WorldBankClient:
    """Download and normalise World Bank indicator observations."""

    def __init__(self, session: requests.Session, timeout_seconds: int = 60) -> None:
        self._session = session
        self._timeout_seconds = timeout_seconds
        self._base_url = "https://api.worldbank.org/v2"

    def fetch(
        self, request: WorldBankRequest
    ) -> tuple[bytes, pd.DataFrame, str, dict[str, object]]:
        """Fetch one indicator and return raw JSON, a long table, and the request URL."""

        url = f"{self._base_url}/country/{request.country_code}/indicator/{request.indicator_code}"
        params: dict[str, str | int] = {
            "date": f"{request.start_year}:{request.end_year}",
            "format": "json",
            "per_page": 1000,
        }
        response = get_bytes(
            self._session,
            url,
            params=params,
            timeout_seconds=self._timeout_seconds,
        )
        payload: Any = response.json()
        if not isinstance(payload, list) or len(payload) < 2 or not isinstance(payload[1], list):
            raise ValueError("Unexpected World Bank API response structure")

        records: list[dict[str, object]] = []
        for item in payload[1]:
            if not isinstance(item, dict):
                continue
            year_text = item.get("date")
            if not isinstance(year_text, str) or not year_text.isdigit():
                continue
            records.append(
                {
                    "country_code": request.country_code,
                    "indicator_code": request.indicator_code,
                    "year": int(year_text),
                    "value": item.get("value"),
                    "unit": item.get("unit") or "",
                    "source_note": item.get("obs_status") or "",
                }
            )
        frame = pd.DataFrame.from_records(records).sort_values("year").reset_index(drop=True)
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
        request: WorldBankRequest,
        raw_json: bytes,
        frame: pd.DataFrame,
        request_url: str,
        http_metadata: dict[str, object],
        root: Path,
        *,
        overwrite: bool,
    ) -> tuple[Path, Path]:
        """Persist raw and tabular snapshots with provenance metadata."""

        stem = (
            f"{request.country_code}_{request.indicator_code}_"
            f"{request.start_year}_{request.end_year}"
        )
        raw_path = root / "data/raw/live/world_bank" / f"{stem}.json"
        csv_path = root / "data/raw/live/world_bank" / f"{stem}.csv"
        atomic_write_bytes(raw_path, raw_json, overwrite=overwrite)
        atomic_write_bytes(
            csv_path,
            frame.to_csv(index=False, lineterminator="\n").encode(),
            overwrite=overwrite,
        )
        atomic_write_json(
            raw_path.with_suffix(".metadata.json"),
            {
                "source": "World Bank Indicators API v2",
                "request_url": sanitise_url(request_url, ()),
                "extracted_at_utc": utc_now_iso(),
                **http_metadata,
                "raw_sha256": sha256_file(raw_path),
                "csv_sha256": sha256_file(csv_path),
                "rows": len(frame),
                "parameters": request.__dict__,
            },
            overwrite=overwrite,
        )
        return raw_path, csv_path


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
        "api_version": "World Bank Indicators API v2",
        "source_licence": "subject_to_world_bank_data_terms",
        "access_conditions": "public_api",
        "territorial_definition": "World Bank country and indicator metadata",
        "units": "indicator_specific",
    }
