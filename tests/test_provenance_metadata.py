from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from portugal_external_growth.io_utils import sha256_file

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


def test_committed_metadata_uses_portable_repository_paths() -> None:
    root = Path(__file__).resolve().parents[1]
    windows_path = re.compile(r"[A-Za-z]:\\")

    for path in sorted(root.rglob("*.metadata.json")):
        if any(part in {".git", ".tmp", ".venv"} for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8")
        assert not windows_path.search(text), f"{path.relative_to(root)} contains absolute path"


def test_committed_metadata_input_artifact_hashes_are_current() -> None:
    root = Path(__file__).resolve().parents[1]

    for path in sorted(root.rglob("*.metadata.json")):
        if any(part in {".git", ".tmp", ".venv"} for part in path.parts):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        input_artifacts = payload.get("input_artifacts", [])
        assert isinstance(input_artifacts, list)
        for artifact in input_artifacts:
            artifact_path = artifact.get("path")
            recorded_sha256 = artifact.get("sha256")
            assert artifact_path, f"{path.relative_to(root)} has input artifact without path"
            assert recorded_sha256, f"{path.relative_to(root)} has input artifact without SHA-256"
            source_path = root / artifact_path
            assert source_path.is_file(), (
                f"{path.relative_to(root)} input artifact is not a file: {artifact_path}"
            )
            actual_sha256 = sha256_file(source_path)
            assert recorded_sha256 == actual_sha256, (
                f"{path.relative_to(root)} has stale hash for {artifact_path}"
            )
