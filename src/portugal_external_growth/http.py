"""HTTP utilities with retries and explicit response validation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass(frozen=True)
class HttpResponse:
    """Normalised HTTP response used by source clients."""

    url: str
    status_code: int
    headers: dict[str, str]
    content: bytes

    def json(self) -> Any:
        """Decode response content as JSON."""

        return json.loads(self.content.decode("utf-8"))


def build_session() -> requests.Session:
    """Create a requests session with conservative retry behaviour."""

    retry = Retry(
        total=5,
        connect=5,
        read=5,
        backoff_factor=1.0,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": "portugal-external-growth/0.1.0"})
    return session


def get_bytes(
    session: requests.Session,
    url: str,
    *,
    params: dict[str, str | int] | None,
    timeout_seconds: int,
) -> HttpResponse:
    """Execute a GET request and return validated response bytes."""

    response = session.get(url, params=params, timeout=timeout_seconds)
    response.raise_for_status()
    return HttpResponse(
        url=response.url,
        status_code=response.status_code,
        headers={str(key): str(value) for key, value in response.headers.items()},
        content=response.content,
    )
