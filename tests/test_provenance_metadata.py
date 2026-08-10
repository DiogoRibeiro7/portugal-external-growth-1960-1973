from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

import pandas as pd
import pytest

from portugal_external_growth.config import load_yaml
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


def test_committed_csv_metadata_describes_own_artifact() -> None:
    root = Path(__file__).resolve().parents[1]

    for path in sorted(root.rglob("*.csv.metadata.json")):
        if any(part in {".git", ".tmp", ".venv"} for part in path.parts):
            continue
        csv_path = Path(str(path)[: -len(".metadata.json")])
        assert csv_path.is_file(), f"{path.relative_to(root)} has no matching CSV"
        payload = json.loads(path.read_text(encoding="utf-8"))
        frame = pd.read_csv(csv_path)
        assert payload.get("sha256") == sha256_file(csv_path), (
            f"{path.relative_to(root)} has stale own-artifact SHA-256"
        )
        assert payload.get("rows") == len(frame), f"{path.relative_to(root)} has stale row count"
        assert payload.get("columns") == [str(column) for column in frame.columns], (
            f"{path.relative_to(root)} has stale column list"
        )


def test_release_version_metadata_is_synchronised() -> None:
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    citation = load_yaml(root / "CITATION.cff")
    zenodo = json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))
    package_init = (root / "src/portugal_external_growth/__init__.py").read_text(encoding="utf-8")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    version = project["version"]

    assert f'__version__ = "{version}"' in package_init
    assert str(citation["version"]) == version
    assert zenodo["version"] == version
    assert f"## [{version}]" in changelog


def test_committed_metadata_source_files_are_resolvable_paths_or_uris() -> None:
    root = Path(__file__).resolve().parents[1]

    for path in sorted(root.rglob("*.metadata.json")):
        if any(part in {".git", ".tmp", ".venv"} for part in path.parts):
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        source_files = payload.get("source_files", [])
        assert isinstance(source_files, list)
        for source_file in source_files:
            assert isinstance(source_file, str)
            if re.match(r"^[a-z][a-z0-9+.-]*://", source_file):
                continue
            assert (root / source_file).exists(), (
                f"{path.relative_to(root)} source file does not resolve: {source_file}"
            )
