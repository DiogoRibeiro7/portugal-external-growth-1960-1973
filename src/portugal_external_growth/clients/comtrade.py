"""UN Comtrade API client for annual merchandise trade."""

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
class ComtradeRequest:
    """Parameters for one bounded Comtrade extraction."""

    year: int
    reporter_code: int
    partner_codes: tuple[int, ...]
    flow_code: str
    commodity_code: str = "TOTAL"
    classification_code: str = "S1"
    max_records: int = 500


class ComtradeClient:
    """Access preview or free-key UN Comtrade endpoints."""

    def __init__(
        self,
        session: requests.Session,
        *,
        timeout_seconds: int = 60,
        subscription_key: str | None = None,
    ) -> None:
        self._session = session
        self._timeout_seconds = timeout_seconds
        self._subscription_key = subscription_key

    def fetch(self, request: ComtradeRequest) -> tuple[bytes, pd.DataFrame, str]:
        """Fetch annual records for one flow and year."""

        endpoint = "data/v1/get" if self._subscription_key else "public/v1/preview"
        url = f"https://comtradeapi.un.org/{endpoint}/C/A/{request.classification_code}"
        params: dict[str, str | int] = {
            "period": request.year,
            "reporterCode": request.reporter_code,
            "partnerCode": ",".join(str(code) for code in request.partner_codes),
            "flowCode": request.flow_code,
            "cmdCode": request.commodity_code,
            "maxRecords": request.max_records,
        }
        if self._subscription_key:
            params["subscription-key"] = self._subscription_key

        response = get_bytes(
            self._session,
            url,
            params=params,
            timeout_seconds=self._timeout_seconds,
        )
        payload: Any = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected UN Comtrade response structure")
        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError("UN Comtrade response does not contain a data list")
        frame = pd.json_normalize(data)
        return response.content, frame, response.url

    def save(
        self,
        request: ComtradeRequest,
        raw_json: bytes,
        frame: pd.DataFrame,
        request_url: str,
        root: Path,
        *,
        overwrite: bool,
    ) -> tuple[Path, Path]:
        """Persist raw Comtrade data and extraction metadata."""

        stem = (
            f"PRT_{request.year}_{request.flow_code}_{request.classification_code}_"
            f"{request.commodity_code}"
        )
        raw_path = root / "data/raw/live/comtrade" / f"{stem}.json"
        csv_path = root / "data/raw/live/comtrade" / f"{stem}.csv"
        atomic_write_bytes(raw_path, raw_json, overwrite=overwrite)
        atomic_write_bytes(
            csv_path,
            frame.to_csv(index=False, lineterminator="\n").encode(),
            overwrite=overwrite,
        )
        atomic_write_json(
            raw_path.with_suffix(".metadata.json"),
            {
                "source": "UN Comtrade",
                "request_url": sanitise_url(request_url, (self._subscription_key or "",)),
                "extracted_at_utc": utc_now_iso(),
                "raw_sha256": sha256_file(raw_path),
                "csv_sha256": sha256_file(csv_path),
                "rows": len(frame),
                "parameters": {
                    **request.__dict__,
                    "partner_codes": list(request.partner_codes),
                },
                "endpoint_mode": "free_key" if self._subscription_key else "preview",
            },
            overwrite=overwrite,
        )
        return raw_path, csv_path
