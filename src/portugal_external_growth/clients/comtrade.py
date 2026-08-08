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


@dataclass(frozen=True)
class ComtradeProductRequest:
    """Parameters for one subscription-key product extraction request."""

    year: int
    reporter_code: int
    partner_code: int
    flow_code: str
    commodity_codes: tuple[str, ...]
    classification_code: str = "S1"
    max_records: int = 250000
    aggregate_by: str | None = None
    breakdown_mode: str = "classic"
    include_desc: bool = True


class ComtradeAPIError(ValueError):
    """Raised when UN Comtrade returns an application-level error."""


class ComtradeSubscriptionKeyRequired(ValueError):
    """Raised when a research extraction is attempted without a subscription key."""


class ComtradePartialResponseError(ValueError):
    """Raised when Comtrade reports more records than a bounded request can return."""


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

    def fetch(self, request: ComtradeRequest) -> tuple[bytes, pd.DataFrame, str, dict[str, object]]:
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
        error = payload.get("error")
        if error:
            raise ComtradeAPIError(f"UN Comtrade API error: {error}")
        data = payload.get("data")
        if not isinstance(data, list):
            raise ValueError("UN Comtrade response does not contain a data list")
        frame = pd.json_normalize(data)
        return (
            response.content,
            frame,
            response.url,
            _http_provenance(
                response,
                endpoint=url,
                query_parameters=params,
                subscription_key=self._subscription_key,
            ),
        )

    def fetch_product_count(self, request: ComtradeProductRequest) -> int:
        """Count product-level records before downloading a bounded request."""

        self._require_subscription_key()
        raw, _frame, _url, _metadata = self._fetch_product(request, count_only=True)
        payload: Any = raw.json()
        count = payload.get("count")
        if not isinstance(count, int):
            raise ValueError("UN Comtrade count response is missing integer count")
        return count

    def fetch_product(
        self, request: ComtradeProductRequest
    ) -> tuple[bytes, pd.DataFrame, str, dict[str, object]]:
        """Fetch product-level final data with a subscription key and truncation check."""

        self._require_subscription_key()
        expected_count = self.fetch_product_count(request)
        if expected_count > request.max_records:
            raise ComtradePartialResponseError(
                f"UN Comtrade request would return {expected_count} records, "
                f"above maxRecords={request.max_records}; split the query further."
            )
        response, frame, url, metadata = self._fetch_product(request, count_only=False)
        payload: Any = response.json()
        actual_count = payload.get("count")
        if isinstance(actual_count, int) and actual_count > len(frame):
            raise ComtradePartialResponseError(
                f"UN Comtrade returned {len(frame)} rows for count={actual_count}; "
                "response may be partial."
            )
        return response.content, frame, url, metadata

    def _fetch_product(
        self, request: ComtradeProductRequest, *, count_only: bool
    ) -> tuple[Any, pd.DataFrame, str, dict[str, object]]:
        endpoint = "data/v1/get"
        url = f"https://comtradeapi.un.org/{endpoint}/C/A/{request.classification_code}"
        params: dict[str, str | int | bool] = {
            "period": request.year,
            "reporterCode": request.reporter_code,
            "partnerCode": request.partner_code,
            "flowCode": request.flow_code,
            "cmdCode": ",".join(request.commodity_codes),
            "maxRecords": request.max_records,
            "countOnly": count_only,
            "includeDesc": request.include_desc,
            "breakdownMode": request.breakdown_mode,
            "subscription-key": self._subscription_key or "",
        }
        if request.aggregate_by:
            params["aggregateBy"] = request.aggregate_by
        response = get_bytes(
            self._session,
            url,
            params=params,
            timeout_seconds=self._timeout_seconds,
        )
        payload: Any = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Unexpected UN Comtrade response structure")
        error = payload.get("error")
        if error:
            raise ComtradeAPIError(f"UN Comtrade API error: {error}")
        data = payload.get("data", [])
        if not isinstance(data, list):
            raise ValueError("UN Comtrade response does not contain a data list")
        frame = pd.json_normalize(data)
        return (
            response,
            frame,
            response.url,
            _http_provenance(
                response,
                endpoint=url,
                query_parameters=params,
                subscription_key=self._subscription_key,
            ),
        )

    def save_product_response(
        self,
        request: ComtradeProductRequest,
        raw_json: bytes,
        frame: pd.DataFrame,
        request_url: str,
        http_metadata: dict[str, object],
        root: Path,
        *,
        overwrite: bool,
    ) -> tuple[Path, Path]:
        """Persist one product-level raw response and flattened snapshot."""

        stem = (
            f"PRT_{request.year}_{request.flow_code}_{request.classification_code}_"
            f"P{request.partner_code}_{_commodity_stem(request.commodity_codes)}"
        )
        raw_path = root / "data/raw/live/comtrade_product" / f"{stem}.json"
        csv_path = root / "data/raw/live/comtrade_product" / f"{stem}.csv"
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
                "purpose": "product_level_research_extraction",
                "request_url": sanitise_url(request_url, (self._subscription_key or "",)),
                "extracted_at_utc": utc_now_iso(),
                **http_metadata,
                "raw_sha256": sha256_file(raw_path),
                "csv_sha256": sha256_file(csv_path),
                "rows": len(frame),
                "parameters": {
                    **request.__dict__,
                    "commodity_codes": list(request.commodity_codes),
                },
                "endpoint_mode": "subscription_final_data",
            },
            overwrite=overwrite,
        )
        return raw_path, csv_path

    def _require_subscription_key(self) -> None:
        if not self._subscription_key:
            raise ComtradeSubscriptionKeyRequired(
                "COMTRADE_SUBSCRIPTION_KEY is required for product-level research extraction."
            )

    def save(
        self,
        request: ComtradeRequest,
        raw_json: bytes,
        frame: pd.DataFrame,
        request_url: str,
        http_metadata: dict[str, object],
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
                **http_metadata,
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

    def save_availability_response(
        self,
        request: ComtradeRequest,
        raw_json: bytes,
        frame: pd.DataFrame,
        request_url: str,
        http_metadata: dict[str, object],
        root: Path,
        *,
        overwrite: bool,
    ) -> Path:
        """Persist one raw response used for historical coverage auditing."""

        stem = (
            f"PRT_{request.year}_{request.flow_code}_{request.classification_code}_"
            f"{request.commodity_code}_coverage"
        )
        raw_path = root / "data/raw/live/comtrade_availability" / f"{stem}.json"
        atomic_write_bytes(raw_path, raw_json, overwrite=overwrite)
        atomic_write_json(
            raw_path.with_suffix(".metadata.json"),
            {
                "source": "UN Comtrade",
                "purpose": "historical_coverage_audit",
                "request_url": sanitise_url(request_url, (self._subscription_key or "",)),
                "extracted_at_utc": utc_now_iso(),
                **http_metadata,
                "raw_sha256": sha256_file(raw_path),
                "rows": len(frame),
                "parameters": {
                    **request.__dict__,
                    "partner_codes": list(request.partner_codes),
                },
                "endpoint_mode": "free_key" if self._subscription_key else "preview",
            },
            overwrite=overwrite,
        )
        return raw_path


def _http_provenance(
    response: Any,
    *,
    endpoint: str,
    query_parameters: dict[str, str | int | bool],
    subscription_key: str | None,
) -> dict[str, object]:
    redacted_parameters = {
        key: ("***REDACTED***" if key == "subscription-key" and subscription_key else value)
        for key, value in query_parameters.items()
    }
    return {
        "endpoint": endpoint,
        "query_parameters": redacted_parameters,
        "http_status": response.status_code,
        "content_type": response.headers.get("Content-Type", "application/json")
        or "application/json",
        "etag": response.headers.get("ETag", ""),
        "last_modified": response.headers.get("Last-Modified", ""),
        "api_version": "UN Comtrade API v1",
        "source_licence": "subject_to_un_comtrade_terms",
        "access_conditions": "preview_or_subscription_api",
        "territorial_definition": "UN Comtrade partner trade/customs/statistical area codes",
        "units": "current_us_dollars",
    }


def _commodity_stem(commodity_codes: tuple[str, ...]) -> str:
    joined = "-".join(commodity_codes)
    return joined[:80].replace(",", "-").replace("/", "_")
