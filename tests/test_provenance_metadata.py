from __future__ import annotations

import json
from pathlib import Path

import pytest

REQUIRED_HTTP_FIELDS = {
    "endpoint",
    "query_parameters",
    "http_status",
    "content_type",
    "etag",
    "last_modified",
    "api_version",
    "source_licence",
    "access_conditions",
    "territorial_definition",
    "units",
}


@pytest.mark.parametrize(
    "directory",
    [
        "data/raw/live/world_bank",
        "data/raw/live/comtrade",
        "data/raw/live/comtrade_availability",
        "data/raw/live/bpstat",
    ],
)
def test_committed_raw_api_metadata_contains_http_provenance(directory: str) -> None:
    root = Path(__file__).resolve().parents[1]
    metadata_files = sorted((root / directory).glob("*.metadata.json"))
    if not metadata_files:
        pytest.skip(f"No committed metadata files under {directory}")

    for path in metadata_files:
        payload = json.loads(path.read_text(encoding="utf-8"))
        missing = REQUIRED_HTTP_FIELDS.difference(payload)
        assert not missing, f"{path.relative_to(root)} missing {sorted(missing)}"
        assert isinstance(payload["query_parameters"], dict)
        assert payload["http_status"] == 200
        assert payload["content_type"]
